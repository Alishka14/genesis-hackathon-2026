"""Evaluator-side JSONL trajectories and exact raw action replay."""
import copy
import json
from pathlib import Path

from .canonical import bounded_json


class FlightRecorder:
    def __init__(self, env):
        self.env = env
        self.rows = []
        self.initial = None

    def reset(self, seed, config):
        self.rows.clear()
        self.initial = None
        obs, info = self.env.reset(seed, config)
        self.initial = copy.deepcopy(obs)
        return obs, info

    @property
    def deadline(self):
        return self.env.deadline

    @property
    def final_score(self):
        return self.env.final_score

    def _record(self, action, transition):
        obs, reward, terminated, truncated, _ = transition
        self.rows.append({"episode_id": self.initial["manifest"]["episode_id"],
                          "step": len(self.rows) + 1, "action": copy.deepcopy(action),
                          "observation": copy.deepcopy(obs), "reward": reward,
                          "terminated": terminated, "truncated": truncated})
        return transition

    def step(self, action):
        if not bounded_json(action):
            raise ValueError("action exceeds recorder limits")
        return self._record(action, self.env.step(action))

    def abort(self, reason):
        # No action was admitted for this supervisor event.
        return self._record(None, self.env.abort(reason))

    def write(self, path):
        with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
            for row in self.rows:
                stream.write(json.dumps(row, ensure_ascii=True, allow_nan=False) + "\n")


def verify_replay(env, seed, config, initial, rows):
    """Verify admitted actions literally. Wall-clock/supervisor events need external timing."""
    recorder = FlightRecorder(env)
    replay_initial, _ = recorder.reset(seed, config)
    if replay_initial != initial:
        raise ValueError("initial replay mismatch")
    for expected in rows:
        if expected["action"] is None and expected["truncated"]:
            raise ValueError("supervisor event needs an external clock or process replay")
        recorder.step(expected["action"])
        if recorder.rows[-1] != expected:
            raise ValueError("transition replay mismatch")
    return recorder.final_score
