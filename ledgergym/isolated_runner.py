"""Experimental Docker-isolated agent runner for trusted local evaluation.

The Docker daemon and host kernel are part of the trust boundary. This is not
proven secure for hostile production workloads or contest infrastructure.
Only the agent script is mounted, and scoring remains on the host.
"""
import copy
import json
import os
from pathlib import Path
import selectors
import secrets
import shutil
import subprocess
import tempfile
import time
from .env import LedgerSandbox
from .score import evaluate

IMAGE = 'python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5'
_MAX_ACTION_BYTES = 65536


def _check_action_shape(value):
    stack = [(value, 0)]
    seen = 0
    while stack:
        item, depth = stack.pop()
        seen += 1
        if depth > 32 or seen > 4096:
            raise ValueError('action structure exceeds limits')
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def run_isolated_agent(public, truth, agent_path, *, timeout=60):
    """Run a line-delimited JSON agent in a restricted container.

    Agent receives {observation, reward, terminated, truncated, info} and
    writes one JSON action per line. Result and truth remain evaluator-side.
    No arbitrary host directories or Docker socket are mounted. Requires a
    local Docker daemon and the exact pinned image; no image pull is attempted.
    """
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise ValueError('invalid timeout')
    source = Path(agent_path)
    if not source.is_file() or source.stat().st_size > 1024 * 1024:
        raise ValueError('invalid agent script')
    public_ids = {v for rows in public['tables'].values() for row in rows for key, v in row.items() if key.endswith('_id') and isinstance(v, str)}
    scores = []
    def scorer(findings, steps):
        result = evaluate(truth['issues'], findings, public_ids, steps)
        scores.append(result)
        return result
    env = LedgerSandbox(public, scorer, closed=True, timeout=timeout)
    initial, info = env.reset()
    actions = []
    name = 'ledgergym-agent-' + secrets.token_hex(12)
    deadline = time.monotonic() + timeout
    process = None
    with tempfile.TemporaryDirectory(prefix='ledgergym-agent-') as directory:
        os.chmod(directory, 0o755)
        mounted = Path(directory) / 'agent.py'
        shutil.copyfile(source, mounted)
        os.chmod(mounted, 0o644)
        command = ['docker', 'run', '--rm', '-i', '--pull=never', '--name', name,
                   '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--pids-limit', '32',
                   '--memory', '256m', '--memory-swap', '256m', '--cpus', '0.5',
                   '--user', '65534:65534', '--shm-size', '8m',
                   '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m',
                   '--mount', f'type=bind,src={mounted},dst=/agent.py,readonly',
                   IMAGE, 'python', '-I', '-u', '/agent.py']
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            reader = selectors.DefaultSelector()
            writer = selectors.DefaultSelector()
            reader.register(process.stdout, selectors.EVENT_READ)
            writer.register(process.stdin, selectors.EVENT_WRITE)
            buffer = bytearray()
            def send(message):
                payload = json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
                while payload:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not writer.select(remaining):
                        raise TimeoutError()
                    written = os.write(process.stdin.fileno(), payload)
                    payload = payload[written:]
            def receive():
                while True:
                    pos = buffer.find(b'\n')
                    if pos >= 0:
                        if pos > _MAX_ACTION_BYTES:
                            raise ValueError('action too large')
                        line = bytes(buffer[:pos])
                        del buffer[:pos + 1]
                        return json.loads(line)
                    if len(buffer) > _MAX_ACTION_BYTES:
                        raise ValueError('action too large')
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not reader.select(remaining):
                        raise TimeoutError()
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        raise EOFError()
                    buffer.extend(chunk)
            message = {'observation': initial, 'reward': 0.0, 'terminated': False, 'truncated': False, 'info': info}
            while True:
                send(message)
                action = receive()
                _check_action_shape(action)
                actions.append(copy.deepcopy(action))
                observation, reward, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    if observation.get('status') == 'invalid_submit':
                        return {'outcome': 'invalid_submit', 'score': {'reward': -1.0}, 'actions': actions}
                    return {'outcome': 'truncated' if truncated else 'terminated', 'score': scores[-1], 'actions': actions}
                message = {'observation': observation, 'reward': reward, 'terminated': terminated, 'truncated': truncated, 'info': info}
        except TimeoutError:
            if not env.done:
                env._finish([], truncated=True)
            return {'outcome': 'timeout', 'score': scores[-1], 'actions': actions}
        except (BrokenPipeError, EOFError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, OverflowError):
            return {'outcome': 'protocol_error', 'score': None, 'actions': actions}
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                try:
                    subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
                    cleanup_deadline = time.monotonic() + 5
                    while True:
                        check = subprocess.run(['docker', 'ps', '-aq', '--filter', f'name=^/{name}$'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False)
                        if check.returncode == 0 and not check.stdout.strip():
                            break
                        if time.monotonic() >= cleanup_deadline:
                            raise RuntimeError('could not verify container cleanup')
                        time.sleep(0.1)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise RuntimeError('could not verify container cleanup') from exc


def main():
    import argparse
    from .episode_io import load_public_episode
    parser = argparse.ArgumentParser(description='Run an experimental Docker-isolated agent on a local fixture.')
    parser.add_argument('episode', help='trusted fixture directory containing public/ and private/')
    parser.add_argument('agent', help='Python agent script implementing the line-delimited JSON protocol')
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    root = Path(args.episode)
    public = load_public_episode(root / 'public')
    truth = json.loads((root / 'private' / 'truth.json').read_text(encoding='utf-8'))
    print(json.dumps(run_isolated_agent(public, truth, args.agent, timeout=args.timeout), sort_keys=True))


if __name__ == '__main__':
    main()
