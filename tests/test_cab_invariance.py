"""CAB-03 and CAB-04: financial-model row and opaque-ID invariance."""
import copy

import pytest

from ledgergym.cab_invariance import (
    transform_financial_episode, validate_cab_invariant,
)
from ledgergym.company_world import build_company
from ledgergym.settlement_faults_v2 import build_settlement_fault_episode


@pytest.mark.parametrize("seed", [7, 42, 2026])
def test_legacy_company_reconciliation_survives_id_and_record_shuffle(seed):
    public, truth, _ = build_company(seed, {
        "postings": 200, "documents": 20,
        "faults": {"duplicate_invoice": 1, "payment_allocation": 1},
    })
    original_public = copy.deepcopy(public)
    original_truth = copy.deepcopy(truth)
    check = validate_cab_invariant(public, truth, seed=seed + 100)
    assert check["status"] == "PASS"
    assert check["reconciliation_score_unchanged"] is True
    assert check["private_mapping_exported"] is False
    assert public == original_public and truth == original_truth


@pytest.mark.parametrize("fault", [
    "duplicate_invoice", "payment_allocation", "duplicate_allocation",
])
def test_v2_settlements_cab_public_financial_invariance(fault):
    public, truth, _ = build_settlement_fault_episode(1234, {
        "postings": 200, "documents": 20, "fault": fault,
    })
    transformed, updated_truth = transform_financial_episode(
        public, truth, seed=404)
    assert transformed != public
    assert transformed["manifest"]["episode_id"] != public["manifest"]["episode_id"]
    assert len(transformed["tables"]["ledger"]) == len(public["tables"]["ledger"])
    assert len(updated_truth["issues"]) == len(truth["issues"])
    check = validate_cab_invariant(public, truth, seed=404)
    assert check["status"] == "PASS"
    assert check["validated_model"] == "accrual_company_v2"


def test_cab_rejects_unsupported_inputs():
    with pytest.raises(ValueError, match="seed"):
        transform_financial_episode({}, {}, seed="2026")
    with pytest.raises(ValueError, match="opaque"):
        transform_financial_episode({"tables": {}}, {}, seed=1)
