"""Trusted, offline research report for a generated LedgerGym 10+10 dataset.

Reads private truth ONLY in the trusted local evaluator. Exports aggregate
counts, never raw truth, issue IDs, seeds or per-episode validity labels.
Outputs cannot be mounted into an untrusted closed-mode policy.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter
import json
from pathlib import Path
import re

from .baselines import run_baseline
from .episode_io import load_public_episode
from .research_diagnostics import (
    EQT, FP_TYPES, STANDARD_VALID, SUSPICIOUS_BUT_VALID,
    evidence_taxonomy, false_accusation_analysis,
)
from .research_robustness import score_invariance_matrix
from .score import accessible_evidence_ids, evaluate


KINDS = {
    "synthetic_company_development",
    "synthetic_company_development_with_settlements",
}
POLICIES = ("seeded_random", "reconciliation", "mark_all", "oracle")


def _submitted_findings(result, truth, policy):
    if policy == "oracle":
        return [
            {
                "type": issue["type"],
                "affected_ids": list(issue["affected_ids"]),
                "claimed_amount_minor": issue["expected_amount_minor"],
                "currency": issue["currency"],
                "evidence_ids": list(issue["allowed_evidence_sets"][0]),
                "explanation": "",
            }
            for issue in truth["issues"]
        ]
    trajectory = result["trajectory"]
    if (not isinstance(trajectory, list) or not trajectory
            or trajectory[-1].get("action") != "submit"):
        raise ValueError("baseline did not finish with a submit")
    return trajectory[-1]["findings"]


def _clean_opportunity(public, truth):
    """One documented clean company is one labelled evaluation opportunity.

    The label requires **zero** private issues. The v2 clean settlement
    generator is specifically a split/refund hard negative, while an ordinary
    v1 clean company is classified as standard valid. This intentionally
    does NOT purport to label every correct sub-operation in faulty episodes.
    """
    if truth["issues"]:
        return {}
    model = public["policy"].get("accounting_model")
    if model not in {"accrual_company_v1", "accrual_company_v2"}:
        return {}
    ids = [
        row[key]
        for table, key in (("invoices", "invoice_id"), ("payments", "payment_id"))
        for row in public["tables"][table] if isinstance(row.get(key), str)
    ]
    if not ids:
        return {}
    return {
        "one_verified_clean_company": {
            "kind": (SUSPICIOUS_BUT_VALID if model == "accrual_company_v2"
                     else STANDARD_VALID),
            "affected_ids": ids,
        }
    }


def analyse_development_dataset(dataset, output, *, trials=8):
    """Create a new aggregate report; all data and labels remain local."""
    if type(trials) is not int or not 1 <= trials <= 100:
        raise ValueError("trials must be 1..100")
    dataset = Path(dataset).expanduser().resolve(strict=True)
    index_path = dataset / "index.json"
    if index_path.is_symlink() or not index_path.resolve(strict=True).is_relative_to(dataset):
        raise ValueError("unsafe dataset index")
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes.decode("utf-8"))
    if index.get("kind") not in KINDS:
        raise ValueError("expected a 10+10 synthetic company dataset")
    output = Path(output).expanduser().resolve()
    if output.exists() or output == dataset or output.is_relative_to(dataset):
        raise ValueError("report must be a new directory outside the dataset")

    stats = {
        policy: {
            "episodes": 0, "score_matches": 0,
            "tp": 0, "fp": 0, "fn": 0,
            "eqt": Counter({tag: 0 for tag in EQT}),
            "faa": Counter({tag: 0 for tag in FP_TYPES}),
            "standard_opportunities": 0,
            "standard_cases_with_fp": 0,
            "hard_negative_opportunities": 0,
            "hard_negative_cases_with_fp": 0,
            "invariance_trials_passed": 0,
        }
        for policy in POLICIES
    }
    identities = set()
    clean = {"standard": 0, "hard_negative": 0, "faulty": 0}
    for split in ("train", "dev"):
        entries = index.get(split)
        if not isinstance(entries, list) or len(entries) != 10:
            raise ValueError("invalid 10+10 split")
        for entry in entries:
            rel = entry.get("path")
            if not isinstance(rel, str) or not re.fullmatch(
                    rf"{split}/episode-[0-9]{{2}}", rel):
                raise ValueError("invalid episode location")
            root = (dataset / rel).resolve(strict=True)
            if not root.is_relative_to(dataset):
                raise ValueError("episode escapes dataset")
            public = load_public_episode(root / "public")
            truth_path = root / "private" / "truth.json"
            if truth_path.is_symlink() or not truth_path.resolve(strict=True).is_relative_to(root):
                raise ValueError("linked or unsafe evaluator truth")
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            if public["manifest"]["episode_id"] != entry.get("episode_id"):
                raise ValueError("index/episode mismatch")
            if entry["episode_id"] in identities:
                raise ValueError("duplicate episode across splits")
            identities.add(entry["episode_id"])
            if not isinstance(truth.get("issues"), list):
                raise ValueError("invalid trusted truth")
            if public["policy"].get("accounting_model") == "accrual_company_v1":
                from .company_checks import validate_company
                validate_company(public, truth)
            elif public["policy"].get("accounting_model") == "accrual_company_v2":
                from .settlement_faults_v2 import validate_settlement_episode
                validate_settlement_episode(public, truth)
            else:
                raise ValueError("unsupported accounting model")
            annotations = _clean_opportunity(public, truth)
            if truth["issues"]:
                clean["faulty"] += 1
            elif annotations and next(iter(annotations.values()))["kind"] == SUSPICIOUS_BUT_VALID:
                clean["hard_negative"] += 1
            else:
                clean["standard"] += 1
            public_ids = accessible_evidence_ids(public)
            for policy in POLICIES:
                result = run_baseline(public, truth, policy, seed=0)
                findings = _submitted_findings(result, truth, policy)
                steps = (len(result["trajectory"]) - 1
                         if result["trajectory"] is not None else 0)
                official = evaluate(truth["issues"], findings, public_ids, steps)
                if official != result["score"]:
                    raise ValueError("baseline official score changed")
                eqt = evidence_taxonomy(truth["issues"], findings, public_ids)
                faa = false_accusation_analysis(
                    truth["issues"], findings, public_ids,
                    case_annotations=annotations, inspection_steps=steps,
                )
                if sum(faa["fp_subtypes"].values()) != official["fp"]:
                    raise ValueError("false accusation partition differs")
                inv = score_invariance_matrix(
                    truth["issues"], findings, public_ids,
                    inspection_steps=steps, trials=trials, seed=2026,
                )
                aggregate = stats[policy]
                aggregate["episodes"] += 1
                aggregate["score_matches"] += 1
                aggregate["tp"] += official["tp"]
                aggregate["fp"] += official["fp"]
                aggregate["fn"] += official["fn"]
                aggregate["eqt"].update(eqt["counts"])
                aggregate["faa"].update(faa["fp_subtypes"])
                aggregate["invariance_trials_passed"] += inv["passed"]
                s = faa["case_level"]["standard_valid_case_fpr"]
                h = faa["case_level"]["hard_negative_case_fpr"]
                aggregate["standard_opportunities"] += s["opportunities"]
                aggregate["standard_cases_with_fp"] += s["cases_with_fp"]
                aggregate["hard_negative_opportunities"] += h["opportunities"]
                aggregate["hard_negative_cases_with_fp"] += h["cases_with_fp"]

    report = {
        "kind": "ledgergym_evaluator_only_research_diagnostics_v1",
        "dataset_kind": index["kind"],
        "dataset_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "episodes": len(identities),
        "clean_case_counts": clean,
        "policies": {},
        "private_truth_exported": False,
        "official_score_modified": False,
        "contest_certified": False,
        "limitations": [
            "Only synthetic development episodes; no independent holdout.",
            "Reconciliation shares the public model checks with the generator.",
            "Clean-case FPR counts one opportunity per entirely clean company.",
            "EQT temporal/contradiction tags are not inferred without extra verified annotations.",
            "Invariance probes cover the scorer, not a learned policy.",
        ],
    }
    for policy, measure in stats.items():
        measure["eqt"] = dict(measure["eqt"])
        measure["faa"] = dict(measure["faa"])
        measure["standard_valid_case_fpr"] = (
            measure["standard_cases_with_fp"] / measure["standard_opportunities"]
            if measure["standard_opportunities"] else None
        )
        measure["hard_negative_case_fpr"] = (
            measure["hard_negative_cases_with_fp"] / measure["hard_negative_opportunities"]
            if measure["hard_negative_opportunities"] else None
        )
        if measure["episodes"] != 20 or measure["score_matches"] != 20:
            raise ValueError("incomplete baseline evidence")
        if sum(measure["faa"].values()) != measure["fp"]:
            raise ValueError("aggregate FAA partition invalid")
        if measure["invariance_trials_passed"] != 20 * trials:
            raise ValueError("incomplete invariance matrix")
        report["policies"][policy] = measure
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    (output / "research_summary.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="generated synthetic 10+10 dataset")
    parser.add_argument("output", help="new external aggregate report directory")
    parser.add_argument("--trials", type=int, default=8)
    args = parser.parse_args()
    try:
        report = analyse_development_dataset(args.dataset, args.output,
                                             trials=args.trials)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(f"research diagnostics not verified: {type(exc).__name__}")
    print(json.dumps({
        "status": "PASS", "episodes": report["episodes"],
        "research_report": str(Path(args.output).resolve()),
        "private_truth_exported": False, "contest_certified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
