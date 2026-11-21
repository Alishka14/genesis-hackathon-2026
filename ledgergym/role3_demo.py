"""Run a trusted local walkthrough or a real isolated file-fed walkthrough."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import judge_adapter
from examples.role3_policy import investigate
from .flight_recorder import FlightRecorder, verify_replay
from .isolated_runner import IMAGE, run_file_agent


def _has_image():
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def demo(args, root):
    cfg = {"mode": "closed", "episode_dir": str(root), "team_config": {}}
    if args.mode == "restricted":
        if not _has_image():
            print(json.dumps({"status": "NOT_RUN", "reason": "Local Docker and pinned image required."}))
            return 2
        policy = Path(__file__).resolve().parents[1] / "examples" / "role3_policy.py"
        result = run_file_agent(27, cfg, policy)
        if result["outcome"] != "terminated":
            print(json.dumps({"status": "CONFIRMED_FAIL", "outcome": result["outcome"]}))
            return 1
        initial, rows, score = result["initial"], result["trajectory"], result["score"]
    else:
        recorder = FlightRecorder(judge_adapter.make_env())
        initial, _ = recorder.reset(27, cfg)
        policy = investigate(initial)
        action = next(policy)
        while True:
            obs, _, terminated, truncated, _ = recorder.step(action)
            if terminated or truncated:
                break
            action = policy.send(obs)
        rows, score = recorder.rows, recorder.final_score
    replay = verify_replay(judge_adapter.make_env(), 27, cfg, initial, rows)
    envelope = rows[-1]["action"]["args"]["findings"]
    if score != replay or score != judge_adapter.score_episode(root, envelope, len(rows) - 1):
        raise ValueError("score replay mismatch")
    if args.trajectory:
        with args.trajectory.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=True, allow_nan=False) + "\n")
    print(json.dumps({"status": "VERIFIED_PASS", "mode": args.mode, "replay": "exact",
                      "actions": [row["action"]["name"] for row in rows], "score": score}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("local", "restricted"))
    parser.add_argument("--episode", type=Path)
    parser.add_argument("--trajectory", type=Path)
    args = parser.parse_args()
    if args.episode:
        return demo(args, args.episode)
    if args.mode == "restricted":
        parser.error("restricted mode requires --episode")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "episode"
        judge_adapter.generate_episode(27, {"scenario": "duplicate_invoice", "fault": False}, root)
        return demo(args, root)


if __name__ == "__main__":
    raise SystemExit(main())
