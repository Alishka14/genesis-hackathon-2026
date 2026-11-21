"""Reproducible offline integration gate for the LedgerGym stacked PRs.

Runs focused/full pytest, a mixed 10+10 company dataset and six controlled
causal pairs. Produces a *sanitized* result report containing no episode files,
truth labels, findings, provenance, secrets or subprocess test output.

This cannot replace an organizer evaluation or the platform's Docker checks.
Use --mode full and the separate existing Docker/offline CI job before release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FOCUSED = [
    "tests/test_v2_causal_pairs.py",
    "tests/test_v2_independent_truth.py",
    "tests/test_v2_pair_dataset.py",
    "tests/test_company_settlements_v2.py",
    "tests/test_settlement_dataset_benchmark.py",
    "tests/test_matcher_p0_regression.py",
    "tests/test_local_financial_matrix.py",
]


def _run(label: str, args: list[str], *, timeout: int, cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    print(f"[{label}] running", flush=True)
    try:
        completed = subprocess.run(
            args, cwd=cwd, timeout=timeout, capture_output=True, text=True,
            check=False,
        )
        passed = completed.returncode == 0
        if not passed:
            # Diagnostics are emitted only to the trusted operator's console;
            # they are NOT written into the shareable result JSON.
            print((completed.stdout + "\n" + completed.stderr)[-6500:], file=sys.stderr)
        status = "pass" if passed else "fail"
        return {"status": status, "exit_code": completed.returncode,
                "duration_sec": round(time.monotonic() - started, 3)}
    except subprocess.TimeoutExpired:
        print(f"[{label}] timeout", file=sys.stderr)
        return {"status": "timeout", "exit_code": None,
                "duration_sec": round(time.monotonic() - started, 3)}


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("report not a JSON object")
    return data


def _assert_company_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("kind") != "synthetic_company_development_with_settlements":
        raise ValueError("wrong mixed dataset type")
    if summary.get("replay") != {"trajectories": 60, "score_matches": 60}:
        raise ValueError("mixed baseline action replay mismatch")
    expected_models = {"accrual_company_v1": 8, "accrual_company_v2": 2}
    expected_labels = {"clean": 1, "faulty": 1}
    for split in ("train", "dev"):
        if summary["model_counts"][split] != expected_models:
            raise ValueError("unexpected train/dev model counts")
        if summary["v2_label_counts"][split] != expected_labels:
            raise ValueError("v2 labels accidentally imbalanced")
        for name in ("seeded_random", "reconciliation", "mark_all", "oracle"):
            if summary["splits"][split][name]["episodes"] != 10:
                raise ValueError("missing baseline episode")
    for name in ("reconciliation", "oracle"):
        if summary["policies"][name]["mean_f1"] != 1:
            raise ValueError("perfect reference baseline failed")
    clean = summary["clean_false_accusations"]
    for model in ("accrual_company_v1", "accrual_company_v2"):
        if clean["overall"][model]["reconciliation"]["fp"] != 0:
            raise ValueError("reconciliation falsely accuses a clean episode")
    return {"episodes": 20, "replayed_trajectories": 60,
            "models_per_split": expected_models, "v2_labels_per_split": expected_labels}


def _assert_pair_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("kind") != "internal_v2_causal_pairs_v1" or summary.get("pairs") != 6:
        raise ValueError("causal pair count mismatch")
    if len(summary.get("modes", {})) != 6:
        raise ValueError("missing causal scenario")
    for name in ("reconciliation", "oracle"):
        entry = summary["policies"][name]
        if entry["pairs"] != 6 or entry["both_correct"] != 6 or entry["fault_tp"] != 8:
            raise ValueError("causal sensitivity regression")
        if entry["clean_fp"] != 0 or entry["paired_accuracy"] != 1:
            raise ValueError("false accusation or causal mismatch")
    return {"paired_comparisons": 6, "total_variants": 12,
            "audited_fault_issues": 8, "clean_false_accusations": 0}


def _audit_tracked_private_files() -> dict[str, Any]:
    """Fail closed if evaluator-only synthetic answer files are tracked by Git."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=False,
            capture_output=True,
        )
    except OSError:
        return {"status": "fail", "reason": "git_unavailable"}
    if completed.returncode != 0:
        return {"status": "fail", "reason": "git_index_unavailable"}
    names = [part.decode("utf-8", errors="replace").replace("\\", "/")
             for part in completed.stdout.split(b"\x00") if part]
    forbidden = []
    for name in names:
        parts = name.split("/")
        if (name.endswith("/private/truth.json")
                or name.endswith("/private/provenance.json")
                or name.endswith("/private_pair_index.json")
                or name == "private_pair_index.json"
                or parts[-1] in {".env", ".envrc"}):
            forbidden.append(name)
    if forbidden:
        print("Tracked evaluator-only files (remove from Git index): "
              + ", ".join(forbidden[:10]), file=sys.stderr)
    return {"status": "fail" if forbidden else "pass",
            "tracked_count": len(names), "forbidden_count": len(forbidden)}


def verify(*, mode: str, report_path: Path, timeout: int) -> int:
    if mode not in {"focused", "full"} or timeout < 1:
        raise ValueError("invalid gate configuration")
    if sys.version_info < (3, 11):
        raise RuntimeError("LedgerGym requires Python 3.11+")
    report: dict[str, Any] = {
        "gate": "ledgergym-offline-integration-v1",
        "verification_level": mode,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "stages": {},
        "success": False,
        "contest_certified": False,
        # A full pytest run does not prove Docker tests ran rather than
        # being skipped. The separate role3 workflow must enforce that gate.
        "docker_isolation_covered": False,
        "offline_bundle_covered": False,
    }
    stages = report["stages"]
    test_paths = FOCUSED if mode == "focused" else ["tests"]
    try:
        stages["tracked_private_files"] = _audit_tracked_private_files()
        stages["pytest"] = _run(
            "pytest", [sys.executable, "-m", "pytest", "-q", "-rs",
                       "-p", "no:cacheprovider", *test_paths],
            timeout=timeout, cwd=ROOT,
        )
        with tempfile.TemporaryDirectory(prefix="ledgergym-release-") as temp:
            temp_root = Path(temp)
            mixed = temp_root / "mixed"
            paired = temp_root / "paired"
            stages["mixed_generator"] = _run(
                "mixed_generator",
                [sys.executable, "-m", "ledgergym.company_dataset",
                 str(mixed), "--seed", "2026",
                 "--settlement-hard-negatives", "--evaluate"],
                timeout=timeout, cwd=ROOT,
            )
            if stages["mixed_generator"]["status"] == "pass":
                try:
                    metrics = _assert_company_metrics(_read_json(mixed / "evaluation" / "summary.json"))
                    stages["mixed_generator"]["metrics"] = metrics
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    print(f"Invalid mixed dataset metrics: {type(exc).__name__}: {exc}", file=sys.stderr)
                    stages["mixed_generator"]["status"] = "fail"
            stages["causal_pairs"] = _run(
                "causal_pairs",
                [sys.executable, "-m", "ledgergym.v2_pair_dataset",
                 str(paired), "--seed", "2026", "--evaluate"],
                timeout=timeout, cwd=ROOT,
            )
            if stages["causal_pairs"]["status"] == "pass":
                try:
                    metrics = _assert_pair_metrics(_read_json(paired / "evaluation" / "summary.json"))
                    stages["causal_pairs"]["metrics"] = metrics
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    print(f"Invalid paired benchmark metrics: {type(exc).__name__}: {exc}", file=sys.stderr)
                    stages["causal_pairs"]["status"] = "fail"
        report["success"] = all(entry["status"] == "pass" for entry in stages.values())
        # This gate is not a release approval even if every local stage passes.
        return_code = 0 if report["success"] else 1
        return return_code
    finally:
        report_path = report_path.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"success": report["success"], "report": str(report_path),
                          "verification_level": mode}, sort_keys=True), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline release integration diagnostics; not an organizer certification.")
    parser.add_argument("--mode", choices=["focused", "full"], default="focused")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per stage")
    parser.add_argument("--report", type=Path, default=Path("ledgergym-integration-report.json"))
    args = parser.parse_args()
    raise SystemExit(verify(mode=args.mode, report_path=args.report, timeout=args.timeout))


if __name__ == "__main__":
    main()
