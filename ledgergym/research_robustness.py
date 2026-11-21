"""Trusted property-style and anti-shortcut probes for the audit matcher.

Pure deterministic transformations; no Hypothesis, external APIs or new
production dependencies. This is evaluator-side diagnostic code only.
"""
from __future__ import annotations

import copy
import random

from .score import evaluate


def score_invariance_matrix(issues, findings, public_ids, *,
                            inspection_steps=0, trials=40, seed=2026):
    """Check row-independent scorer behavior under permutations and bijective IDs.

    This checks the official *matcher*, not a model's generalization. Only
    public IDs are remapped, and private issue_id stays evaluator-only.
    """
    if type(trials) is not int or not 1 <= trials <= 10000:
        raise ValueError("trials must be 1..10000")
    if type(seed) is not int:
        raise ValueError("seed must be int")
    ids = sorted(set(public_ids))
    if not all(isinstance(x, str) and x for x in ids):
        raise ValueError("invalid public identifiers")
    before = evaluate(issues, findings, set(ids), inspection_steps)
    rng = random.Random(seed)
    for index in range(trials):
        public = ids[:]
        rng.shuffle(public)
        # Names are deliberately opaque, independent of semantic content.
        # A source ID may already equal a generated one; use an impossible
        # namespace shared by no source IDs to preserve the bijection.
        prefix = "audit-remap:"
        while any(value.startswith(prefix) for value in ids):
            prefix = "_" + prefix
        mapped = {value: f"{prefix}{i:05d}" for i, value in enumerate(public)}
        renamed_issues = copy.deepcopy(issues)
        renamed_findings = copy.deepcopy(findings)
        for issue in renamed_issues:
            issue["affected_ids"] = [mapped.get(x, x) for x in issue["affected_ids"]]
            issue["allowed_evidence_sets"] = [
                [mapped.get(x, x) for x in group]
                for group in issue["allowed_evidence_sets"]
            ]
            rng.shuffle(issue["affected_ids"])
            for group in issue["allowed_evidence_sets"]:
                rng.shuffle(group)
            rng.shuffle(issue["allowed_evidence_sets"])
        for finding in renamed_findings:
            finding["affected_ids"] = [
                mapped.get(x, x) for x in finding["affected_ids"]
            ]
            finding["evidence_ids"] = [
                mapped.get(x, x) for x in finding["evidence_ids"]
            ]
            rng.shuffle(finding["affected_ids"])
            rng.shuffle(finding["evidence_ids"])
        rng.shuffle(renamed_issues)
        rng.shuffle(renamed_findings)
        current = evaluate(renamed_issues, renamed_findings, set(mapped.values()),
                           inspection_steps)
        if current != before:
            raise AssertionError(
                f"invariance probe failure at trial={index} seed={seed}"
            )
    return {
        "method": "evaluator_only_score_invariance_v1",
        "trials": trials, "passed": trials,
        "seed": seed,
        "baseline": {key: before[key] for key in ("tp", "fp", "fn", "f1", "reward")},
        "scope": "matcher_only; not policy generalization",
    }


def shrink_counterexample(items, reproduces, *, max_calls=200):
    """Deterministic ddmin for a sequence that reproduces a failure.

    The predicate must return True for a reproducing input. The function
    never mutates its input, does not claim global minimality, and reports
    whether its one-element-deletion check was exhausted by the call budget.
    """
    if not isinstance(items, (list, tuple)):
        raise TypeError("items must be a sequence")
    if type(max_calls) is not int or not 1 <= max_calls <= 10000:
        raise ValueError("max_calls must be 1..10000")
    current = list(items)
    calls = 0

    def probe(candidate):
        nonlocal calls
        if calls >= max_calls:
            return None
        calls += 1
        return bool(reproduces(list(candidate)))

    if probe(current) is not True:
        raise ValueError("initial counterexample does not reproduce")
    granularity = 2
    while len(current) >= 2 and calls < max_calls:
        span = (len(current) + granularity - 1) // granularity
        shrunk = False
        for start in range(0, len(current), span):
            candidate = current[:start] + current[start + span:]
            outcome = probe(candidate)
            if outcome is None:
                break
            if outcome:
                current = candidate
                granularity = max(2, granularity - 1)
                shrunk = True
                break
        if not shrunk:
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)

    # A final one-element pass, if budget permits, makes the result
    # deletion-minimal within the remaining budget. Do not assert that it is
    # globally minimal if the budget ran out.
    one_minimal = True
    while current:
        shortened = False
        for index in range(len(current)):
            outcome = probe(current[:index] + current[index + 1:])
            if outcome is None:
                one_minimal = False
                break
            if outcome:
                current.pop(index)
                shortened = True
                break
        if not one_minimal or not shortened:
            break
    return {
        "minimal": current,
        "original_count": len(items),
        "reduced_count": len(current),
        "calls": calls,
        "deletion_minimal_verified": one_minimal,
        "method": "deterministic_ddmin_v1",
    }
