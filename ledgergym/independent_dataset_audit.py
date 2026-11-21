"""Trusted-only independent audit of a local synthetic 10+10 dataset.

Reads private/truth.json *inside this trusted CLI process*, never copies it or
prints issue identifiers, seeds, provenance or individual customer records.
For open development sets; NOT a blinded judge test or external-accountant
certification. Keep DATASET PRIVATE. Only share the aggregate report.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from .episode_io import load_public_episode
from .independent_finance_audit import audit_company


def audit_dataset(root):
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("linked or invalid private dataset")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    if index.get("kind") not in {
        "synthetic_company_development",
        "synthetic_company_development_with_settlements",
    }:
        raise ValueError("not an open synthetic company dataset")
    checked, count_issues, models, clean_count = 0, 0, Counter(), 0
    seen_paths, seen_ids = set(), set()
    for split in ("train", "dev"):
        entries = index.get(split)
        if not isinstance(entries, list) or len(entries) != 10:
            raise ValueError("expected exactly 10 train + 10 dev episodes")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("malformed index episode")
            path = entry.get("path")
            episode_id = entry.get("episode_id")
            if not isinstance(path, str) or not re.fullmatch(
                    rf"{split}/episode-[0-9]{{2}}", path):
                raise ValueError("untrusted index path")
            if (not isinstance(episode_id, str) or not episode_id
                    or path in seen_paths or episode_id in seen_ids):
                raise ValueError("duplicate index path or episode")
            seen_paths.add(path)
            seen_ids.add(episode_id)
            target = root / path
            if target.is_symlink() or (target / "private").is_symlink() or (
                    target / "public").is_symlink():
                raise ValueError("linked episode path forbidden")
            target = target.resolve(strict=True)
            if not target.is_relative_to(root):
                raise ValueError("episode escapes dataset")
            public = load_public_episode(target / "public")
            if public["manifest"]["episode_id"] != entry.get("episode_id"):
                raise ValueError("index/episode ID mismatch")
            source = target / "private" / "truth.json"
            if source.is_symlink():
                raise ValueError("linked private truth forbidden")
            truth = json.loads(source.read_text(encoding="utf-8"))
            result = audit_company(public, truth)
            if result["status"] != "PASS" or result["journal_net_minor"] != 0:
                raise ValueError("independent financial audit failed")
            checked += 1
            count_issues += result["issues_audited"]
            models[result["model"]] += 1
            clean_count += int(not truth["issues"])
    return {
        "status": "PASS",
        "scope": "open_synthetic_development_only",
        "independent_code_path": True,
        "independent_external_accountant": False,
        "contest_certified": False,
        "episodes_audited": checked,
        "issues_reconciled": count_issues,
        "clean_episodes": clean_count,
        "accounting_models": dict(sorted(models.items())),
        "private_truth_exported": False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dataset", help="TRUSTED dataset with private truth; do not upload it")
    ap.add_argument("--report", help="optional new path for aggregate-only JSON")
    args = ap.parse_args()
    summary = audit_dataset(args.dataset)
    if args.report:
        output = Path(args.report).expanduser()
        with output.open("x", encoding="utf-8") as stream:
            json.dump(summary, stream, sort_keys=True, indent=2)
            stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
