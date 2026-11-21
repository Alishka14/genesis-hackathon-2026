import json
import shutil
import subprocess
import sys

import pytest

from ledgergym.canonical import JudgeEnv
from ledgergym.flight_recorder import FlightRecorder, verify_replay
from ledgergym.isolated_runner import IMAGE, run_file_agent, _drive, _docker_command
from role3_fixture import write_case


@pytest.fixture
def case(tmp_path):
    write_case(tmp_path, 7)
    return {"mode": "closed", "episode_dir": str(tmp_path), "team_config": {}}


def run_test_policy(script, config, timeout=4):
    # A trusted test child exercises real pipe I/O only. This is not a sandbox test.
    env = FlightRecorder(JudgeEnv(timeout=timeout))
    initial, info = env.reset(72, config)
    # A policy may terminate while the parent has buffered stdin data.
    # Popen's context-manager exit implicitly flushes stdin and can raise
    # BrokenPipeError even when _drive correctly classified a protocol fault.
    child = subprocess.Popen([sys.executable, "-u", "-c", script], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    try:
        result = _drive(child, env, initial, info)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        for pipe in (child.stdin, child.stdout):
            if pipe is not None:
                try:
                    pipe.close()
                except (BrokenPipeError, OSError):
                    pass
    return result, env


@pytest.mark.parametrize(("script", "outcome"), [
    ("import sys; sys.stderr.write('SECRET-CRASH'); sys.exit(17)", "protocol_error"),
    ("print('malformed')", "protocol_error"),
    ("print('['*1800 + ']'*1800)", "protocol_error"),
    ("print('x' * (2*1024*1024+1))", "protocol_error"),
    ("print('NaN')", "protocol_error"),
    ("import time; time.sleep(5)", "timeout"),
])
def test_real_pipe_faults(case, script, outcome):
    result, recorder = run_test_policy(script, case, timeout=.5 if outcome == "timeout" else 4)
    assert result == outcome and recorder.final_score["fn"] == 1
    assert recorder.final_score["tp"] == 0 and recorder.final_score["return"] == -1.
    assert recorder.rows[-1]["truncated"] and recorder.rows[-1]["reward"] == 0
    assert "SECRET" not in json.dumps(recorder.rows)
    with pytest.raises(RuntimeError):
        recorder.step({"name": "submit", "args": {}})


def test_pipe_terminal_and_recorded_replay(case):
    script = """import json,sys
initial=json.loads(input())['observation']
print(json.dumps({'name':'unknown','args':{}}))
assert json.loads(input())['observation']['remaining_steps']==99
print(json.dumps({'name':'submit','args':{'findings':{'episode_id':initial['manifest']['episode_id'],'findings':[]}}}))
"""
    result, rec = run_test_policy(script, case)
    assert result == "terminated" and rec.rows[-1]["observation"]["result"] == {"accepted": True}
    assert verify_replay(JudgeEnv(), 72, case, rec.initial, rec.rows) == rec.final_score
    rec.rows[0]["reward"] = 1
    with pytest.raises(ValueError, match="replay"):
        verify_replay(JudgeEnv(), 72, case, rec.initial, rec.rows)


def test_mount_and_limits(tmp_path):
    script = tmp_path / "policy.py"
    cmd = _docker_command("test", script)
    assert cmd.count("--mount") == 1 and cmd[cmd.index("--mount") + 1] == f"type=bind,src={script},dst=/agent.py,readonly"
    for flag in ["--network", "--read-only", "--cap-drop", "--memory", "--pids-limit", "--cpus", "--pull=never"]:
        assert flag in cmd
    assert cmd[cmd.index("--network") + 1] == "none" and IMAGE in cmd
    assert "docker.sock" not in " ".join(cmd)


def available():
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not available(), reason="local Docker daemon and pinned image required")
@pytest.mark.parametrize("behavior", ["submit", "crash", "timeout", "malformed", "train_file", "train_generated", "missing_image"])
def test_container_boundary_and_cleanup(case, tmp_path, behavior, monkeypatch):
    policy = tmp_path / "policy.py"
    path = str(tmp_path / "private/truth.json")
    scripts = {
        "submit": """import json,os,sys
initial=json.loads(input())
assert initial['reward']==0 and initial['info']=={}
assert not os.path.exists(%r) and not os.path.exists('/var/run/docker.sock')
# Check effective restrictions rather than OS-dependent sysfs interface
# enumeration and statvfs mount flags (Docker Desktop/VM differences).
import socket
probe=socket.socket()
probe.settimeout(.3)
try:
    try:
        probe.connect(('203.0.113.1', 9))
    except OSError:
        pass
    else:
        raise AssertionError('outbound network connection succeeded')
finally:
    probe.close()
try:
    with open('/ledgergym-root-write-probe', 'wb') as marker:
        marker.write(b'x')
except OSError:
    pass
else:
    raise AssertionError('root filesystem is writable')
print(json.dumps({'name':'submit','args':{'findings':{'episode_id':initial['observation']['manifest']['episode_id'],'findings':[]}}}))
message=json.loads(input())
assert message['terminated'] and message['reward']==EXPECTED_REWARD and message['info']=={}
""" % path, "crash": "raise SystemExit(7)", "timeout": "import time; time.sleep(60)", "malformed": "print('not JSON')"}
    if behavior == "train_file":
        case["mode"] = "train"
    if behavior == "train_generated":
        case = {"mode":"train","team_config":{"scenario":"duplicate_invoice","fault":False}}
    if behavior == "missing_image":
        monkeypatch.setattr("ledgergym.isolated_runner.IMAGE", "ledgergym-missing-image:role3-test-unavailable")
    expected_reward = {"train_file":-1., "train_generated":1.}.get(behavior, 0.)
    script = scripts.get(behavior, scripts["submit"]).replace("EXPECTED_REWARD", str(expected_reward))
    policy.write_text(script, encoding="utf-8")
    result = run_file_agent(72, case, policy, timeout=4 if behavior == "timeout" else 15)
    assert result["outcome"] == {"crash":"protocol_error","timeout":"timeout","missing_image":"runner_error",
                                 "malformed":"protocol_error"}.get(behavior, "terminated")
    if behavior == "missing_image":
        assert result["score"] is None and not result["trajectory"]
    else:
        assert result["score"]["fn"] == (0 if behavior == "train_generated" else 1)
        assert result["trajectory"][-1]["reward"] == expected_reward
    if result["outcome"] == "terminated":
        assert result["terminal_delivery"] == {"written":True, "policy_exit_code":0}
    listed = subprocess.check_output(["docker", "ps", "-aq", "--filter", f"name=^/{result['container_name']}$"])
    assert listed.strip() == b""
