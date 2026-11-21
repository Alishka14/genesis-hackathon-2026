"""Property-style invariance and reproducible shrinking probes."""
import copy

import pytest

from ledgergym.research_robustness import (
    score_invariance_matrix, shrink_counterexample,
)
from ledgergym.score import evaluate


def _sample():
    issues = [
        {
            "issue_id": "private-0", "type": "duplicate_invoice",
            "affected_ids": ["i0", "i1"], "expected_amount_minor": 1000,
            "currency": "KZT", "allowed_evidence_sets": [["d0", "d1"]],
        },
        {
            "issue_id": "private-1", "type": "payment_allocation",
            "affected_ids": ["p0", "i2"], "expected_amount_minor": 700,
            "currency": "KZT", "allowed_evidence_sets": [["d2", "d3"]],
        },
    ]
    findings = [
        {
            "type": "duplicate_invoice", "affected_ids": ["i1", "i0"],
            "claimed_amount_minor": 1000, "currency": "KZT",
            "evidence_ids": ["d1", "d0", "extra"], "explanation": "",
        },
        {
            "type": "payment_allocation", "affected_ids": ["i2", "p0"],
            "claimed_amount_minor": 700, "currency": "KZT",
            "evidence_ids": ["d3", "d2"], "explanation": "",
        },
        {
            "type": "duplicate_invoice", "affected_ids": ["i1", "i0"],
            "claimed_amount_minor": 1000, "currency": "KZT",
            "evidence_ids": ["d1", "d0"], "explanation": "",
        },
    ]
    ids = {"i0", "i1", "i2", "p0", "d0", "d1", "d2", "d3", "extra"}
    return issues, findings, ids


def test_matcher_invariance_on_200_deterministic_transformations():
    issues, findings, ids = _sample()
    before = (copy.deepcopy(issues), copy.deepcopy(findings))
    original = evaluate(issues, findings, ids, 7)
    result = score_invariance_matrix(
        issues, findings, ids, trials=200, seed=4321,
        inspection_steps=7,
    )
    assert result["trials"] == result["passed"] == 200
    assert result["baseline"] == {
        "tp": 2, "fp": 1, "fn": 0,
        "f1": original["f1"], "reward": original["reward"],
    }
    assert issues == before[0] and findings == before[1]


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 2026, 4294967295])
def test_permutation_seed_variation_preserves_f1_and_reward(seed):
    issues, findings, ids = _sample()
    assert score_invariance_matrix(
        issues, findings, ids, trials=20,
        seed=seed, inspection_steps=10,
    )["passed"] == 20


def test_minimal_counterexample_shrinks_redundant_operations():
    inputs = [
        "list_records", "get_document", "noise", "dangerous-action", "other",
        "calculator", "submit",
    ]
    predicate = lambda candidate: "dangerous-action" in candidate
    report = shrink_counterexample(inputs, predicate)
    assert report["minimal"] == ["dangerous-action"]
    assert report["original_count"] == 7
    assert report["reduced_count"] == 1
    assert report["deletion_minimal_verified"] is True
    assert report["calls"] > 1
    assert inputs[0] == "list_records"


def test_two_element_interaction_is_preserved_in_shrink():
    inputs = ["a", "required-start", "b", "required-end", "c"]
    def reproduces(items):
        return "required-start" in items and "required-end" in items
    report = shrink_counterexample(inputs, reproduces)
    assert report["minimal"] == ["required-start", "required-end"]
    assert report["deletion_minimal_verified"] is True


def test_failing_or_invalid_reproduction_is_rejected():
    with pytest.raises(ValueError, match="initial counterexample"):
        shrink_counterexample(["a", "b"], lambda candidate: False)
    with pytest.raises(ValueError, match="trials"):
        score_invariance_matrix([], [], set(), trials=0)
    with pytest.raises(ValueError, match="max_calls"):
        shrink_counterexample(["a"], lambda x: True, max_calls=0)


def test_budget_exhaustion_reported_not_claimed_minimal():
    result = shrink_counterexample(
        ["a", "b", "c", "d"],
        lambda candidate: "b" in candidate,
        max_calls=1,
    )
    assert result["calls"] == 1
    assert result["deletion_minimal_verified"] is False
    assert result["minimal"] == ["a", "b", "c", "d"]
