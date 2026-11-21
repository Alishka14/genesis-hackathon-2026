"""Four model-v1 finance fault families, reversible causal flips."""
import pytest

from ledgergym.cab_company_pairs import (
    FAULTS, audit_v1_causal_pair, verify_v1_causal_catalog,
)


@pytest.mark.parametrize("fault", FAULTS)
@pytest.mark.parametrize("seed", [7, 2026])
def test_each_fault_is_same_seed_reversible_causal_flip(fault, seed):
    report = audit_v1_causal_pair(seed, fault)
    assert report["fault_family"] == fault
    assert report["restored_clean_exactly"] is True
    assert report["clean_false_positives"] == 0
    assert report["fault_true_positives"] == 1
    assert report["public_contract_unchanged"] is True
    assert report["private_truth_exported"] is False


def test_cab_v1_catalog_is_complete_for_all_four_families():
    catalog = verify_v1_causal_catalog(seeds=(7,))
    assert catalog["pairs"] == 4
    assert catalog["reversible_pairs"] == 4
    assert catalog["families"] == {kind: 1 for kind in FAULTS}


def test_cab_cannot_claim_success_for_unknown_fault():
    with pytest.raises(ValueError, match="invalid"):
        audit_v1_causal_pair(7, "made_up_fault")
