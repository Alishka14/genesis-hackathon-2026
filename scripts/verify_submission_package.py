"""Read-only integrity audit for the OPEN LedgerGym jury package.

Checks the exported directory alone. No evaluator truth is needed or loaded.
A passing result establishes file integrity and schema, not hidden-test scores.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

PUBLIC_FILES = ("manifest.json", "policy.json", "ledger.csv",
                "invoices.jsonl", "payments.jsonl", "fx.csv")
FIELDS = {"episode_id", "step", "action", "observation", "reward",
          "terminated", "truncated"}
POLICIES = {"seeded_random", "reconciliation", "mark_all"}
KINDS = {"synthetic_company_development",
         "synthetic_company_development_with_settlements"}
PRIVATE = {"truth", "provenance", "seed", "issue_id",
           "allowed_evidence_sets", "expected_amount_minor",
           "interventions", "private_pair_index"}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _check_public(value):
    if isinstance(value, dict):
        if PRIVATE & set(value):
            raise ValueError("private evaluator keys in submission")
        for v in value.values():
            _check_public(v)
    elif isinstance(value, list):
        for v in value:
            _check_public(v)


def verify_public_package(root):
    """Verify exact inventory, SHA-256, 20 episode IDs and 60 complete traces."""
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("package must be a directory")
    if any(entry.is_symlink() for entry in root.rglob("*")):
        raise ValueError("linked submission entry")
    index = _json(root / "index.json")
    if not isinstance(index, dict) or set(index) != {"kind", "train", "dev"}:
        raise ValueError("invalid public index")
    if index["kind"] not in KINDS:
        raise ValueError("wrong public dataset type")
    expected = {"index.json", "README_SUBMISSION.md",
                "SHA256SUMS.json", "trace_index.json", "trajectories.jsonl"}
    ids = {}
    for split in ("train", "dev"):
        entries = index[split]
        if not isinstance(entries, list) or len(entries) != 10:
            raise ValueError("expected 10+10 episodes")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"path", "episode_id"}:
                raise ValueError("invalid index entry")
            relative, episode_id = entry["path"], entry["episode_id"]
            if (not isinstance(relative, str)
                    or not re.fullmatch(rf"{split}/episode-[0-9]{{2}}", relative)
                    or not isinstance(episode_id, str) or not episode_id
                    or episode_id in ids):
                raise ValueError("invalid or duplicated public episode")
            ids[episode_id] = split
            prefix = f"{relative}/public/"
            for name in PUBLIC_FILES:
                expected.add(prefix + name)
            manifest = _json(root / prefix / "manifest.json")
            if not isinstance(manifest, dict) or manifest.get("episode_id") != episode_id:
                raise ValueError("public manifest ID mismatch")
            _check_public(manifest)
            policy = _json(root / prefix / "policy.json")
            _check_public(policy)
            for name in ("invoices.jsonl", "payments.jsonl"):
                for line in (root / prefix / name).read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        _check_public(json.loads(line))
            for name in ("ledger.csv", "fx.csv"):
                with (root / prefix / name).open(encoding="utf-8", newline="") as stream:
                    headers = csv.DictReader(stream).fieldnames
                if not headers or PRIVATE & set(headers):
                    raise ValueError("private column in public CSV")

    present = {entry.relative_to(root).as_posix()
               for entry in root.rglob("*") if entry.is_file()}
    if present != expected:
        raise ValueError("submission file inventory mismatch")
    manifest = _json(root / "SHA256SUMS.json")
    if (not isinstance(manifest, dict)
            or set(manifest) != {"schema", "files"}
            or manifest["schema"] != "ledgergym-public-submission-v1"
            or not isinstance(manifest["files"], dict)
            or set(manifest["files"]) != expected - {"SHA256SUMS.json"}):
        raise ValueError("invalid SHA256 inventory")
    for path, checksum in manifest["files"].items():
        if (not isinstance(checksum, str)
                or not re.fullmatch("[0-9a-f]{64}", checksum)
                or hashlib.sha256((root / path).read_bytes()).hexdigest() != checksum):
            raise ValueError("SHA256 mismatch")

    trace_index = _json(root / "trace_index.json")
    if (not isinstance(trace_index, dict)
            or set(trace_index) != {"format", "closed_mode",
                                   "private_truth_exported", "trajectories"}
            or trace_index["format"] != "ledgergym-public-development-transitions-v1"
            or trace_index["closed_mode"] is not False
            or trace_index["private_truth_exported"] is not False
            or not isinstance(trace_index["trajectories"], list)
            or len(trace_index["trajectories"]) != 60):
        raise ValueError("invalid full trace index")
    _check_public(trace_index)
    records = [json.loads(line)
               for line in (root / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if not records:
        raise ValueError("empty full trace")
    cursor = 0
    seen = set()
    for span in trace_index["trajectories"]:
        if not isinstance(span, dict) or set(span) != {
                "episode_id", "split", "policy", "first_line", "steps"}:
            raise ValueError("invalid trajectory span")
        eid, split, policy = span["episode_id"], span["split"], span["policy"]
        label = (eid, policy)
        steps, first = span["steps"], span["first_line"]
        if (eid not in ids or split != ids[eid] or policy not in POLICIES
                or label in seen
                or type(steps) is not int or steps < 1 or steps > 100
                or type(first) is not int or first != cursor + 1
                or cursor + steps > len(records)):
            raise ValueError("invalid trajectory coverage")
        seen.add(label)
        for step, row in enumerate(records[cursor:cursor + steps], 1):
            if (not isinstance(row, dict) or set(row) != FIELDS
                    or row["episode_id"] != eid
                    or type(row["step"]) is not int or row["step"] != step
                    or not isinstance(row["action"], dict)
                    or not isinstance(row["observation"], dict)
                    or type(row["reward"]) not in (int, float)
                    or not math.isfinite(row["reward"])
                    or type(row["terminated"]) is not bool
                    or type(row["truncated"]) is not bool
                    or row["truncated"] is not False
                    or row["terminated"] is not (step == steps)):
                raise ValueError("invalid seven-field transition")
            _check_public(row)
        cursor += steps
    if len(seen) != 60 or cursor != len(records):
        raise ValueError("incomplete or extra trajectories")
    return {"status": "PASS", "train": 10, "dev": 10,
            "trajectories": len(seen), "transitions": len(records),
            "verified_files": len(expected), "private_truth_exported": False,
            "contest_certified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="public-only exported folder")
    args = parser.parse_args()
    try:
        result = verify_public_package(args.directory)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(f"NOT VERIFIED: {type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
