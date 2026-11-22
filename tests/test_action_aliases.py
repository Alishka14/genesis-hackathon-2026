"""Readings of the case API besides the canonical {"name","args"} envelope."""
import json

import judge_adapter
from ledgergym.canonical import JudgeEnv


def _setup(tmp_path, mode="train"):
    episode = tmp_path / "ep"
    judge_adapter.generate_episode(61, {"faults": {"duplicate_invoice": 1, "fx_rate_or_date": 1}}, episode)
    truth = json.loads((episode / "private" / "truth.json").read_text())
    env = JudgeEnv()
    obs, _ = env.reset(1, {"mode": mode, "episode_dir": str(episode)})
    findings = [{"type": i["type"], "affected_ids": i["affected_ids"], "claimed_amount_minor": i["expected_amount_minor"],
                 "currency": i["currency"], "evidence_ids": i["allowed_evidence_sets"][0], "explanation": ""}
                for i in truth["issues"]]
    return env, obs["manifest"]["episode_id"], findings


def test_flat_read_actions_equal_canonical(tmp_path):
    env, _, _ = _setup(tmp_path)
    canonical = env.step({"name": "list_records", "args": {"table": "ledger", "limit": 3}})
    env2, _, _ = _setup(tmp_path / "b")
    flat = env2.step({"action": "list_records", "table": "ledger", "limit": 3})
    assert flat == canonical and canonical[0]["error"] is None
    assert env2.step({"action": "calculator", "expression": "1.5*2"})[0]["result"] == "3.0"


def test_flat_and_direct_submit_score_like_canonical(tmp_path):
    rewards = []
    for index, make in enumerate([
        lambda eid, f: {"name": "submit", "args": {"findings": {"episode_id": eid, "findings": f}}},
        lambda eid, f: {"name": "submit", "args": {"episode_id": eid, "findings": f}},
        lambda eid, f: {"action": "submit", "episode_id": eid, "findings": f},
    ]):
        env, eid, findings = _setup(tmp_path / str(index))
        obs, reward, terminated, truncated, _ = env.step(make(eid, findings))
        assert obs["result"] == {"accepted": True} and terminated and not truncated
        rewards.append((reward, env.final_score))
    assert rewards[0] == rewards[1] == rewards[2] and rewards[0][1]["f1"] == 1


def test_malformed_aliases_are_still_rejected(tmp_path):
    env, eid, findings = _setup(tmp_path, mode="closed")
    assert env.step({"action": "list_records", "table": "ledger", "bogus": 1})[0]["error"]["code"] == "invalid_action"
    assert env.step({"action": "shell", "cmd": "ls"})[0]["error"]["code"] == "invalid_action"
    assert env.step({"action": "list_records", "name": "x", "args": {}})[0]["error"]["code"] == "invalid_action"
    obs, reward, terminated, _, _ = env.step({"name": "submit", "args": {"episode_id": eid, "findings": findings, "extra": 1}})
    assert terminated and obs["error"]["code"] == "invalid_submit" and env.final_score["return"] == -1


def test_jury_simulation_script_passes(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    done = subprocess.run([sys.executable, str(root / "scripts" / "jury_simulation.py"), str(tmp_path / "jury")],
                          capture_output=True, text=True, timeout=600, cwd=root)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    report = json.loads(done.stdout)
    assert report["simulated_total_out_of_90"] == 90 and report["data"]["correct"] == 20
