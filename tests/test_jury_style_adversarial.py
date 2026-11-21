"""Internal adversarial matrix aligned to GENESIS contract/reward/paired tests.

This is *not* the organizer's 20 hidden cases. It exercises actual generated
v1/v2 financial histories and the public reconciliation policy (not only the
matcher) across independent deterministic seeds and renamed/shuffled IDs.
"""
import copy

import pytest

from ledgergym.cab_invariance import validate_cab_invariant
from ledgergym.company_world import build_company
from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.score import accessible_evidence_ids, evaluate
from ledgergym.settlement_faults_v2 import build_settlement_fault_episode


V1_CASES = (
    {},
    {"faults": {"duplicate_invoice": 1}},
    {"faults": {"payment_allocation": 1}},
    {"faults": {"fx_rate_or_date": 1}},
    {"faults": {"reporting_period": 1}},
    {"compounds": {"fx_allocation": 1}},
    {"compounds": {"duplicate_allocation": 1}},
)


@pytest.mark.parametrize("seed", [7, 42, 2026, 91073])
@pytest.mark.parametrize("config", V1_CASES)
def test_jury_style_company_invariance(seed, config):
    public, truth, _ = build_company(
        seed, {"postings": 200, "documents": 20, **config})
    before = copy.deepcopy((public, truth))
    evidence = validate_cab_invariant(public, truth, seed=seed + 8080)
    assert evidence["status"] == "PASS"
    assert evidence["reconciliation_score_unchanged"] is True
    assert evidence["private_mapping_exported"] is False
    assert (public, truth) == before


@pytest.mark.parametrize("seed", [7, 42, 2026])
@pytest.mark.parametrize("kind", [None, "duplicate_invoice",
                                   "payment_allocation", "duplicate_allocation"])
def test_jury_style_v2_settlement_invariance(seed, kind):
    if kind is None:
        public, truth, _ = build_settlement_company(
            seed, {"postings": 200, "documents": 20})
    else:
        public, truth, _ = build_settlement_fault_episode(
            seed, {"postings": 200, "documents": 20, "fault": kind})
    evidence = validate_cab_invariant(public, truth, seed=seed + 300)
    assert evidence["status"] == "PASS"
    assert evidence["validated_model"] == "accrual_company_v2"


@pytest.mark.parametrize("seed", [7, 42, 2026, 91073])
@pytest.mark.parametrize("fault", [
    "duplicate_invoice", "payment_allocation", "fx_rate_or_date",
    "reporting_period",
])
def test_jury_style_evidence_and_reward_adversarial_attacks(seed, fault):
    public, truth, _ = build_company(
        seed, {"postings": 200, "documents": 20, "faults": {fault: 1}})
    assert len(truth["issues"]) == 1
    issue = truth["issues"][0]
    ids = accessible_evidence_ids(public)
    correct = {
        "type": issue["type"],
        "affected_ids": list(issue["affected_ids"]),
        "claimed_amount_minor": issue["expected_amount_minor"],
        "currency": issue["currency"],
        "evidence_ids": list(issue["allowed_evidence_sets"][0]),
        "explanation": "",
    }
    baseline = evaluate(truth["issues"], [correct], ids, 0)
    assert baseline["tp"] == 1 and baseline["fp"] == baseline["fn"] == 0
    assert baseline["f1"] == baseline["reward"] == 1
    # An extra identical report must not earn a duplicate TP.
    repeat = evaluate(truth["issues"], [correct, correct], ids, 0)
    assert (repeat["tp"], repeat["fp"], repeat["fn"]) == (1, 1, 0)
    assert repeat["reward"] < baseline["reward"]
    # Evidence cannot be inferred from an inaccessible private/foreign ID.
    foreign = copy.deepcopy(correct)
    foreign["evidence_ids"].append("nonpublic-evidence-id")
    wrong_evidence = evaluate(truth["issues"], [foreign], ids, 0)
    assert (wrong_evidence["tp"], wrong_evidence["fp"],
            wrong_evidence["fn"]) == (0, 1, 1)
    # One minor unit off is not accepted by the explicitly exact matcher.
    wrong_amount = copy.deepcopy(correct)
    wrong_amount["claimed_amount_minor"] += 1
    off = evaluate(truth["issues"], [wrong_amount], ids, 0)
    assert (off["tp"], off["fp"], off["fn"]) == (0, 1, 1)
    # Inspection cost only reduces an equal-quality score by 0.002 per step.
    slow = evaluate(truth["issues"], [correct], ids, 3)
    assert slow["reward"] == pytest.approx(0.994)


@pytest.mark.parametrize("seed", [42, 2026])
def test_jury_style_clean_company_false_accusations(seed):
    public, truth, _ = build_company(
        seed, {"postings": 200, "documents": 20})
    assert truth["issues"] == []
    ids = accessible_evidence_ids(public)
    silent = evaluate([], [], ids, 0)
    assert silent["f1"] == 1 and silent["reward"] == 1
    random_row = public["tables"]["ledger"][0]["row_id"]
    accusation = {
        "type": "reporting_period",
        "affected_ids": [random_row],
        "claimed_amount_minor": 1,
        "currency": "KZT",
        "evidence_ids": [random_row],
        "explanation": "",
    }
    noisy = evaluate([], [accusation], ids, 0)
    assert noisy["fp"] == 1 and noisy["tp"] == 0
    assert noisy["f1"] == 0 and noisy["reward"] == -1
