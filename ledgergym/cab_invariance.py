"""Evaluator-only CAB invariance transformations of supported financial episodes.

Renames opaque business identifiers by a global bijection and shuffles public
table row order. Updates all referenced IDs, including private truth references,
ONLY in a trusted testing process. No private mapping reaches the agent.
"""
from __future__ import annotations

import copy
import random


def transform_financial_episode(public, truth, *, seed=2026):
    if type(seed) is not int:
        raise ValueError("seed must be integer")
    rng = random.Random(seed)
    identifiers = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if ((key.endswith("_id") or key in ("service_ref", "episode_id"))
                        and isinstance(item, str) and item):
                    identifiers.add(item)
                elif key.endswith("_ids") and isinstance(item, list):
                    identifiers.update(x for x in item if isinstance(x, str) and x)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(public)
    if not identifiers:
        raise ValueError("no public opaque identifiers to transform")
    prefix = "cab-id:"
    while any(value.startswith(prefix) for value in identifiers):
        prefix = "_" + prefix
    original = sorted(identifiers)
    aliases = [f"{prefix}{index:06d}" for index in range(len(original))]
    rng.shuffle(aliases)
    mapping = dict(zip(original, aliases))

    def remap(value):
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        if isinstance(value, str):
            return mapping.get(value, value)
        return value

    updated_public = remap(copy.deepcopy(public))
    updated_truth = remap(copy.deepcopy(truth))
    for table in ("ledger", "invoices", "payments", "fx"):
        rows = updated_public["tables"][table]
        rng.shuffle(rows)
    return updated_public, updated_truth


def validate_cab_invariant(public, truth, *, seed=2026):
    """Assert financial validity and reconciliation score invariance."""
    model = public["policy"].get("accounting_model")
    if model == "accrual_company_v1":
        from .company_checks import validate_company
        validator = validate_company
    elif model == "accrual_company_v2":
        from .settlement_faults_v2 import validate_settlement_episode
        validator = validate_settlement_episode
    else:
        raise ValueError("CAB only supports versioned company models")
    from .baselines import run_baseline
    validator(public, truth)
    transformed_public, transformed_truth = transform_financial_episode(
        public, truth, seed=seed)
    validator(transformed_public, transformed_truth)

    before = run_baseline(public, truth, "reconciliation", seed=0)["score"]
    after = run_baseline(transformed_public, transformed_truth,
                         "reconciliation", seed=0)["score"]
    # IDs are changed, but all semantic findings/amounts and inspection steps
    # should remain equivalent when the same policy follows the public API.
    if before != after:
        raise AssertionError(f"public policy CAB invariant failed, seed={seed}")
    return {
        "status": "PASS", "seed": seed,
        "baseline": "deterministic_public_reconciliation",
        "validated_model": model,
        "financial_truth_renamed": True,
        "reconciliation_score_unchanged": True,
        "private_mapping_exported": False,
        "contest_certified": False,
    }
