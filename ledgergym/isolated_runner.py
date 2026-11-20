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

from .canonical import JudgeEnv, MAX_ACTION_BYTES, bounded_json
from .env import LedgerSandbox
from .flight_recorder import FlightRecorder
from .score import evaluate

IMAGE = 'python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5'
_MAX_OBSERVATION_BYTES = 8 * 1024 * 1024


def _docker_command(name, script):
    return ["docker", "run", "--rm", "-i", "--pull=never", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL", "--log-driver", "none",
            "--security-opt", "no-new-privileges", "--pids-limit", "32", "--memory", "256m",
            "--memory-swap", "256m", "--cpus", "0.5", "--user", "65534:65534", "--shm-size", "8m",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",
            "--mount", f"type=bind,src={script},dst=/agent.py,readonly",
            IMAGE, "python", "-I", "-u", "/agent.py"]


def _message(obs, reward, terminated, truncated, info):
    return {"observation": obs, "reward": reward, "terminated": terminated,
            "truncated": truncated, "info": info}


def _pipe_worker(process, requests, replies):
    # The trusted supervisor times out independently even if either OS pipe blocks.
    try:
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


def _drive(process, env, initial, info, *, action_limit=MAX_ACTION_BYTES):
    requests = queue.Queue(maxsize=2)
    replies = queue.Queue(maxsize=1)
    worker = threading.Thread(target=_pipe_worker, args=(process, requests, replies), daemon=True)
    worker.start()
    message = _message(initial, 0., False, False, info)
    try:
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
                try:
                    replies.get(timeout=max(0., min(.25, env.deadline - time.monotonic())))
                except queue.Empty:
                    pass
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


def _cleanup(process, name):
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10, check=False)
        check = subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^/{name}$"],
                               capture_output=True, timeout=10, check=True)
        if check.stdout.strip():
            raise RuntimeError("container cleanup unverified")
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("container cleanup unverified") from None
    finally:
        process.stdin.close()
        process.stdout.close()


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
            return "timeout", None
        try:
            process = subprocess.Popen(_docker_command(name, script), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            raise RuntimeError("Docker runner unavailable") from None
        try:
            return _drive(process, env, initial, info, action_limit=action_limit), name
        finally:
            _cleanup(process, name)


def run_file_agent(seed, config, agent_path, *, timeout=60):
    """Return evaluator-only result for the canonical file-fed closed policy."""
    if config.get("mode") != "closed" or "episode_dir" not in config:
        raise ValueError("file-fed closed configuration required")
    env = FlightRecorder(JudgeEnv(timeout=timeout))
    initial, info = env.reset(seed, config)
    outcome, name = _launch(env, initial, info, agent_path, MAX_ACTION_BYTES)
    return {"outcome": outcome, "initial": initial, "trajectory": env.rows,
            "score": env.final_score, "container_name": name}


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
    ids = {v for rows in public["tables"].values() for row in rows for k, v in row.items()
           if k.endswith("_id") and isinstance(v, str)}
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
    outcome, _ = _launch(env, initial, info, agent_path, 65536)
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
    args = parser.parse_args()
    root = Path(args.episode)
    if args.canonical:
        result = run_file_agent(0, {"mode": "closed", "episode_dir": root}, args.agent, timeout=args.timeout)
    else:
        public = load_public_episode(root / "public")
        truth = json.loads((root / "private" / "truth.json").read_text(encoding="utf-8"))
        result = run_isolated_agent(public, truth, args.agent, timeout=args.timeout)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
