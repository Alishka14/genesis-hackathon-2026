"""Run a policy through restricted Docker. Only the policy script is mounted."""
import argparse
import copy
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading
import time

from .canonical import JudgeEnv, MAX_ACTION_BYTES, ResetDeadline, bounded_json
from .env import LedgerSandbox
from .flight_recorder import FlightRecorder
from .score import evaluate
from .record_ids import addressable_ids

IMAGE = 'python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5'
_MAX_OBSERVATION_BYTES = 8 * 1024 * 1024
_READY = b"ledgergym-ready-v1\n"
_BOOT = ("import runpy,sys;sys.stdout.buffer.write(b'ledgergym-ready-v1\\n');"
         "sys.stdout.buffer.flush();runpy.run_path('/agent.py',run_name='__main__')")


def _docker_command(name, script):
    return ["docker", "run", "--rm", "-i", "--pull=never", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL", "--log-driver", "none",
            "--security-opt", "no-new-privileges", "--pids-limit", "32", "--memory", "256m",
            "--memory-swap", "256m", "--cpus", "0.5", "--user", "65534:65534", "--shm-size", "8m",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",
            "--mount", f"type=bind,src={script},dst=/agent.py,readonly",
            IMAGE, "python", "-I", "-u", "-c", _BOOT]


def _message(obs, reward, terminated, truncated, info):
    return {"observation": obs, "reward": reward, "terminated": terminated,
            "truncated": truncated, "info": info}


def _pipe_worker(process, requests, replies, require_ready):
    # The trusted supervisor times out independently even if either OS pipe blocks.
    try:
        if require_ready:
            ready = process.stdout.readline(len(_READY) + 1) == _READY
            replies.put((ready, None))
            if not ready:
                return
        while True:
            item = requests.get()
            if item is None:
                return
            message, terminal, limit = item
            wire = json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
            if len(wire) > _MAX_OBSERVATION_BYTES:
                raise ValueError()
            process.stdin.write(wire + b"\n")
            process.stdin.flush()
            if terminal:
                replies.put((True, None))
                return
            line = process.stdout.readline(limit + 2)
            if not line.endswith(b"\n") or len(line) - 1 > limit:
                raise ValueError()
            action = json.loads(line.decode("utf-8"))
            if not bounded_json(action):
                raise ValueError()
            replies.put((True, action))
    except (ValueError, UnicodeError, OSError, RecursionError, OverflowError):
        replies.put((False, None))


def _drive(process, env, initial, info, *, action_limit=MAX_ACTION_BYTES, require_ready=False,
           diagnostics=None, workers=None):
    requests = queue.Queue(maxsize=2)
    replies = queue.Queue(maxsize=1)
    worker = threading.Thread(target=_pipe_worker, args=(process, requests, replies, require_ready), daemon=True)
    if workers is not None:
        workers.append(worker)
    worker.start()
    message = _message(initial, 0., False, False, info)
    try:
        if require_ready:
            # Only the trusted image bootstrap emits this marker before invoking
            # the policy. An OCI/daemon failure and a policy exiting 125 differ.
            try:
                ready, _ = replies.get(timeout=max(0., env.deadline - time.monotonic()))
            except queue.Empty:
                return "runner_error"
            if not ready:
                return "runner_error"
        while True:
            left = env.deadline - time.monotonic()
            if left <= 0:
                raise queue.Empty
            requests.put_nowait((message, False, action_limit))
            valid, action = replies.get(timeout=left)
            if time.monotonic() >= env.deadline:
                raise queue.Empty
            if not valid:
                env.abort("protocol_error")
                return "protocol_error"
            obs, reward, terminated, truncated, info = env.step(action)
            message = _message(obs, reward, terminated, truncated, info)
            if terminated or truncated:
                # A one-shot policy may already have exited after submit. Its committed
                # action remains final irrespective of its terminal-read behavior.
                requests.put_nowait((message, True, action_limit))
                written, exit_code = False, None
                grace = min(env.deadline, time.monotonic() + 1.5)
                try:
                    written, _ = replies.get(timeout=max(0., grace - time.monotonic()))
                    exit_code = process.wait(timeout=max(0., grace - time.monotonic()))
                except (queue.Empty, subprocess.TimeoutExpired):
                    pass
                if diagnostics is not None:
                    diagnostics.update(written=written, policy_exit_code=exit_code)
                if (obs.get("error") or {}).get("code") == "timeout":
                    return "timeout"
                if (obs.get("error") or {}).get("code") == "invalid_submit" or obs.get("status") == "invalid_submit":
                    return "invalid_submit"
                return "truncated" if truncated else "terminated"
    except queue.Empty:
        env.abort("timeout")
        return "timeout"
    finally:
        requests.put_nowait(None)


def _cleanup(process, name, workers=()):
    client_stopped = False
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        client_stopped = True
    except (OSError, subprocess.SubprocessError):
        pass
    # The daemon owns the workload independently of its client. Require two
    # consecutive successful absence observations to cover a pending launch.
    absent = 0
    for _ in range(4):
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=2, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            check = subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^/{name}$"],
                                   capture_output=True, timeout=2, check=True)
            absent = absent + 1 if not check.stdout.strip() else 0
        except (OSError, subprocess.SubprocessError):
            absent = 0
        if absent >= 2:
            break
        time.sleep(.1)
    if not client_stopped:
        try:
            process.kill()
            process.wait(timeout=1)
            client_stopped = True
        except (OSError, subprocess.SubprocessError):
            pass
    for worker in workers:
        worker.join(timeout=1)
    io_stopped = all(not worker.is_alive() for worker in workers)
    if client_stopped and io_stopped:
        process.stdin.close()
        process.stdout.close()
    if absent < 2 or not client_stopped or not io_stopped:
        raise RuntimeError("container cleanup unverified")


def _launch(env, initial, info, agent_path, action_limit):
    name = "ledgergym-agent-" + secrets.token_hex(12)
    with tempfile.TemporaryDirectory(prefix="ledgergym-agent-") as directory:
        os.chmod(directory, 0o755)
        script = Path(directory) / "agent.py"
        source_path = Path(agent_path)
        if not source_path.is_file():
            raise ValueError("invalid agent script")
        with source_path.open("rb") as source:
            code = source.read(1024 * 1024 + 1)
        if len(code) > 1024 * 1024:
            raise ValueError("invalid agent script")
        script.write_bytes(code)
        os.chmod(script, 0o644)
        if time.monotonic() >= env.deadline:
            env.abort("timeout")
            return "timeout", None, {}
        try:
            process = subprocess.Popen(_docker_command(name, script), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return "runner_error", None, {}
        diagnostics = {}
        workers = []
        try:
            outcome = _drive(process, env, initial, info, action_limit=action_limit, require_ready=True,
                             diagnostics=diagnostics, workers=workers)
            return outcome, name, diagnostics
        finally:
            _cleanup(process, name, workers)


def run_file_agent(seed, config, agent_path, *, timeout=60):
    """Run a canonical closed or train policy; configuration stays in the trusted judge."""
    env = FlightRecorder(JudgeEnv(timeout=timeout))
    try:
        initial, info = env.reset(seed, config)
    except ResetDeadline:
        # No initial observation or policy action existed. A missing trusted
        # truth header leaves the empty findings frozen but metrics unavailable.
        return {"outcome": "timeout", "initial": None, "trajectory": [], "findings": [],
                "score": env.final_score, "container_name": None, "terminal_delivery": {}}
    outcome, name, diagnostics = _launch(env, initial, info, agent_path, MAX_ACTION_BYTES)
    return {"outcome": outcome, "initial": initial, "trajectory": env.rows,
            "score": env.final_score, "container_name": name, "terminal_delivery": diagnostics}


class _NativeSession:
    def __init__(self, env, deadline):
        self.env = env
        self.deadline = deadline
        self.actions = []

    def step(self, action):
        self.actions.append(copy.deepcopy(action))
        return self.env.step(action)

    def abort(self, reason):
        return self.env._finish([], truncated=True)


def run_isolated_agent(public, truth, agent_path, *, timeout=60):
    """Legacy native protocol. Preserve the earlier action and score result shape."""
    if type(timeout) not in (int, float) or not 0 < timeout <= 60:
        raise ValueError("invalid timeout")
    ids = addressable_ids(public)
    scores = []
    def scorer(findings, steps):
        result = evaluate(truth["issues"], findings, ids, steps)
        scores.append(result)
        return result
    native = LedgerSandbox(public, scorer, closed=True, timeout=timeout)
    start = time.monotonic()
    initial, info = native.reset()
    native.started = start
    env = _NativeSession(native, start + timeout)
    outcome, _, _ = _launch(env, initial, info, agent_path, 65536)
    result = None
    if outcome == "invalid_submit":
        result = {"reward": -1.0}
    elif scores and outcome != "protocol_error":
        result = scores[-1]
    return {"outcome": outcome, "actions": env.actions, "score": result}


def main():
    from .episode_io import load_public_episode
    parser = argparse.ArgumentParser(description="Run an isolated policy on a trusted local fixture.")
    parser.add_argument("episode")
    parser.add_argument("agent")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--canonical", action="store_true")
    parser.add_argument("--mode", choices=("closed", "train"), default="closed")
    parser.add_argument("--team-config", type=json.loads, help="generate train input using this JSON object")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    root = Path(args.episode)
    if args.canonical:
        cfg = {"mode": args.mode}
        if args.team_config is not None:
            if args.mode != "train" or args.episode != "-":
                parser.error("generated training uses '-' for episode and --mode train")
            cfg["team_config"] = args.team_config
        else:
            cfg["episode_dir"] = root
        result = run_file_agent(args.seed, cfg, args.agent, timeout=args.timeout)
    else:
        public = load_public_episode(root / "public")
        truth = json.loads((root / "private" / "truth.json").read_text(encoding="utf-8"))
        result = run_isolated_agent(public, truth, args.agent, timeout=args.timeout)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
