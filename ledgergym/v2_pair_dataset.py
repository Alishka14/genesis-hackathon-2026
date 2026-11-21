"""Open v2 causal pair dataset, with a private pair manifest and baseline report.

Each pair shares seed, manifest, policy, IDs and journal, differing only in
controlled, provenance-recorded financial facts. Variant names a/b are neutral;
the fault/clean labels live only in a trusted private_pair_index.json.
"""
import argparse
import json
from pathlib import Path
import random

from .baselines import run_baseline
from .company_world_v2 import build_settlement_company
from .episode_io import export_episode, load_public_episode
from .settlement_faults_v2 import FAULT_TYPES, build_settlement_fault_episode
from .settlement_faults_v2 import validate_settlement_episode


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def create_v2_causal_dataset(root, *, seed=2026):
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    root = Path(root)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    rng = random.Random(f"v2-causal-pairs-v1:{seed}")
    index = {"kind": "internal_v2_causal_pairs_v1", "train": [], "dev": []}
    used_seeds = set()
    for split in ("train", "dev"):
        for number, mode in enumerate(FAULT_TYPES):
            pair_seed = rng.getrandbits(128)
            while pair_seed in used_seeds:
                pair_seed = rng.getrandbits(128)
            used_seeds.add(pair_seed)
            size = {"postings": 200 + 80 * number, "documents": 20 + 20 * number}
            clean = build_settlement_company(pair_seed, size)
            fault = build_settlement_fault_episode(pair_seed, {**size, "fault": mode})
            assert clean[0]["policy"] == fault[0]["policy"]
            assert clean[0]["manifest"] == fault[0]["manifest"]
            labels = ["clean", "faulty"]
            rng.shuffle(labels)
            variants = {}
            for slot, label in zip(("variant-a", "variant-b"), labels):
                content = clean if label == "clean" else fault
                relative = f"{split}/pair-{number:02}/{slot}"
                folder = root / relative
                folder.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                public, truth, provenance = content
                export_episode(folder, public, truth, seed=pair_seed, provenance=provenance)
                variants[label] = relative
            index[split].append({
                "mode": mode, "seed": pair_seed, "episode_id": clean[0]["manifest"]["episode_id"],
                "variants": variants,
            })
    # The index intentionally includes secrets/pair labels, so it is PRIVATE
    # and must never be mounted inside the agent's file system.
    (root / "private_pair_index.json").write_text(_json(index) + "\n", encoding="utf-8")
    return index


def evaluate_v2_causal_dataset(root, report_dir):
    root = Path(root).resolve(strict=True)
    index = json.loads((root / "private_pair_index.json").read_text(encoding="utf-8"))
    if index.get("kind") != "internal_v2_causal_pairs_v1":
        raise ValueError("invalid paired dataset")
    policies = ("seeded_random", "reconciliation", "mark_all", "oracle")
    summary = {"kind": index["kind"], "pairs": 0, "policies": {
        name: {"pairs": 0, "clean_fp": 0, "fault_tp": 0,
               "both_correct": 0, "f1_clean_sum": 0.0, "f1_fault_sum": 0.0}
        for name in policies
    }, "modes": {}}
    seen = set()
    for split in ("train", "dev"):
        if len(index[split]) != len(FAULT_TYPES):
            raise ValueError("incomplete split")
        for pair in index[split]:
            if pair["mode"] not in FAULT_TYPES or set(pair["variants"]) != {"clean", "faulty"}:
                raise ValueError("invalid pairing")
            loaded = {}
            for label, relative in pair["variants"].items():
                path = (root / relative).resolve(strict=True)
                if not path.is_relative_to(root) or path in seen:
                    raise ValueError("reused/outside episode path")
                seen.add(path)
                public = load_public_episode(path / "public")
                truth = json.loads((path / "private/truth.json").read_text(encoding="utf-8"))
                validate_settlement_episode(public, truth)
                loaded[label] = public, truth
            clean, truth_clean = loaded["clean"]
            fault, truth_fault = loaded["faulty"]
            if (truth_clean["issues"] or not truth_fault["issues"]
                    or clean["manifest"] != fault["manifest"]
                    or clean["policy"] != fault["policy"]):
                raise ValueError("invalid causal pairing")
            if {i["type"] for i in truth_fault["issues"]} != (
                    {"duplicate_invoice", "payment_allocation"}
                    if pair["mode"] == "duplicate_allocation"
                    else {pair["mode"]}):
                raise ValueError("unverified causal labels")
            summary["pairs"] += 1
            for name in policies:
                score_clean = run_baseline(clean, truth_clean, name, seed=0)["score"]
                score_fault = run_baseline(fault, truth_fault, name, seed=0)["score"]
                record = summary["policies"][name]
                record["pairs"] += 1
                record["clean_fp"] += score_clean["fp"]
                record["fault_tp"] += score_fault["tp"]
                record["both_correct"] += int(
                    score_clean["fp"] == 0 and score_clean["fn"] == 0
                    and score_fault["fp"] == 0 and score_fault["fn"] == 0)
                record["f1_clean_sum"] += score_clean["f1"]
                record["f1_fault_sum"] += score_fault["f1"]
            summary["modes"][split + "/" + pair["mode"]] = {
                "truth_issues": len(truth_fault["issues"]),
                "public_policy_same": True,
            }
    for record in summary["policies"].values():
        n = record["pairs"]
        if n != summary["pairs"] or n == 0:
            raise ValueError("missing policy evaluations")
        record["paired_accuracy"] = record["both_correct"] / n
        record["mean_f1_clean"] = record.pop("f1_clean_sum") / n
        record["mean_f1_fault"] = record.pop("f1_fault_sum") / n
    report_dir = Path(report_dir)
    report_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    (report_dir / "summary.json").write_text(_json(summary) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Internal causal v2 clean/fault dataset; private labels never belong in agent workspaces.")
    parser.add_argument("output", help="new directory, must not exist")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    index = create_v2_causal_dataset(args.output, seed=args.seed)
    summary = {"kind": index["kind"], "pairs": 2 * len(FAULT_TYPES)}
    if args.evaluate:
        summary["evaluation"] = evaluate_v2_causal_dataset(
            args.output, Path(args.output) / "evaluation")
    print(_json(summary))


if __name__ == "__main__":
    main()
