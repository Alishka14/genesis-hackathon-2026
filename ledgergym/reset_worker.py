"""Trusted one-shot fixture preparation worker. Its pipes never connect to a policy."""
import json
import sys

from . import canonical
from .generator import _default_scenario, generate_episode


def main():
    seed, config = json.load(sys.stdin.buffer)
    if "episode_dir" in config:
        root = config["episode_dir"]
        truth = canonical._load_truth(root)
    else:
        public, truth = generate_episode(seed, _default_scenario(config["team_config"]))
    # Empty findings have no evidence IDs to resolve. Delegate even this special
    # case to the same scorer so unavailable public storage cannot award a false TP.
    empty = canonical.score.evaluate(truth["issues"], [], set(), 0)
    print(json.dumps(canonical._metrics(empty)), flush=True)
    if "episode_dir" in config:
        public = canonical._load_public(root)
    print(json.dumps([public, truth], ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
