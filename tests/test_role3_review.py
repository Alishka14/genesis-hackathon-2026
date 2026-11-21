"""Independent release-review regressions using only synthetic inputs."""
import json
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

from ledgergym import canonical, isolated_runner
from ledgergym.flight_recorder import FlightRecorder, verify_replay
from role3_fixture import write_case


def case(root):
    write_case(root)
    return {"mode": "closed", "episode_dir": str(root), "team_config": {}}


def test_unicode_physical_lines(tmp_path):
    cfg = case(tmp_path)
    path = tmp_path / "public/invoices.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["description"] = "work\u2028fee\u2029total"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    env = canonical.JudgeEnv()
    env.reset(1, cfg)
    assert env.step({"name": "list_records", "args": {"table": "invoices"}})[0]["result"]["records"] == rows


def test_null_budget_action_raw_replay(tmp_path):
    cfg = case(tmp_path)
    rec = FlightRecorder(canonical.JudgeEnv())
    initial, _ = rec.reset(1, cfg)
    for _ in range(99):
        rec.step({"name": "calculator", "args": {"expression": "4"}})
    obs, _, _, tr, _ = rec.step(None)
    assert tr and obs["error"]["code"] == "budget"
    assert verify_replay(canonical.JudgeEnv(), 1, cfg, initial, rec.rows) == rec.final_score


@pytest.mark.parametrize("ready", [False, True])
def test_setup_and_policy_exit_125_are_distinct(tmp_path, ready):
    rec = FlightRecorder(canonical.JudgeEnv())
    initial, info = rec.reset(1, case(tmp_path))
    script = ("import sys;sys.stdout.buffer.write(b'ledgergym-ready-v1\\n');sys.stdout.buffer.flush();"
              if ready else "") + "raise SystemExit(125)"
    with subprocess.Popen([sys.executable, "-u", "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
        outcome = isolated_runner._drive(child, rec, initial, info, require_ready=True)
    assert outcome == ("protocol_error" if ready else "runner_error")
    assert rec.final_score == ({"tp":0,"fp":0,"fn":0,"precision":0.,"recall":0.,"f1":1.,"return":1.} if ready else None)


def test_cleanup_checks_container_after_client_failure(monkeypatch):
    client = Mock()
    client.poll.return_value = None
    client.wait.side_effect = subprocess.TimeoutExpired("docker", 5)
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd[1])
        if calls == ["rm"]:
            raise OSError("transient daemon failure")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    monkeypatch.setattr(isolated_runner.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="cleanup"):
        isolated_runner._cleanup(client, "synthetic-container")
    assert "rm" in calls and "ps" in calls


@pytest.mark.parametrize("generated", [True, False])
def test_train_runner_keeps_judge_config_private(tmp_path, monkeypatch, generated):
    cfg = ({"mode": "train", "team_config":{"scenario":"duplicate_invoice","fault":False}}
           if generated else {**case(tmp_path), "mode":"train"})
    def launch(env, initial, info, agent_path, action_limit):
        step = env.step({"name":"submit", "args":{"findings":{"episode_id":initial["manifest"]["episode_id"],"findings":[]}}})
        assert step[1:] == (1.,True,False,{})
        return "terminated","mock",{"written":True,"policy_exit_code":0}
    monkeypatch.setattr(isolated_runner, "_launch", launch)
    result = isolated_runner.run_file_agent(30,cfg,"unused")
    assert result["score"]["return"] == result["trajectory"][-1]["reward"] == 1


def test_reset_interrupts_blocked_public_load(tmp_path, monkeypatch):
    cfg = case(tmp_path)
    program = """import time
from ledgergym import canonical, reset_worker
def wait(*a):
    time.sleep(15)
canonical.load_public_episode = wait
reset_worker.main()
"""
    monkeypatch.setattr(canonical, "_reset_command", lambda: [sys.executable, "-u", "-c", program], raising=False)
    env = canonical.JudgeEnv(timeout=1.25)
    before = time.monotonic()
    with pytest.raises(TimeoutError):
        env.reset(3, cfg)
    assert time.monotonic() - before < 5
    assert env.final_score["return"] == 1
    with pytest.raises(RuntimeError):
        env.step(None)
    result = isolated_runner.run_file_agent(3, cfg, "never-mounted", timeout=1.25)
    assert result["outcome"] == "timeout" and result["score"]["return"] == 1 and result["initial"] is None


@pytest.mark.parametrize("expected_code", [0, 29])
def test_terminal_peer_observation_is_host_visible(tmp_path, expected_code):
    rec = FlightRecorder(canonical.JudgeEnv())
    initial, info = rec.reset(1, case(tmp_path))
    script = """import json
episode=json.loads(input())['observation']['manifest']['episode_id']
print(json.dumps({'name':'submit','args':{'findings':{'episode_id':episode,'findings':[]}}}),flush=True)
m=json.loads(input())
assert m['terminated'] and m['reward']==0 and m['info']=={}
raise SystemExit(%d)
""" % expected_code
    diagnostics = {}
    with subprocess.Popen([sys.executable,"-u","-c",script],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as child:
        assert isolated_runner._drive(child,rec,initial,info,diagnostics=diagnostics) == "terminated"
    assert diagnostics == {"written":True,"policy_exit_code":expected_code}
    assert rec.final_score["return"] == 1
