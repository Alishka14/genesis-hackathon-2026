import copy
import pytest
from ledgergym.world import make_episode, validate_episode


@pytest.mark.parametrize('seed', [0, 7, 99])
def test_duplicate_and_hard_negative_have_same_amount_but_different_identity(seed):
    faulty, truth = make_episode(seed, fault=True)
    clean, clean_truth = make_episode(seed, fault=False)
    for public in (faulty, clean):
        a, b = public['tables']['invoices']
        assert a['total_minor'] == b['total_minor']
        assert public['policy']['duplicate_rule'] == 'one_invoice_per_service_ref'
        assert a['line_items'][0]['service_ref']
    a, b = faulty['tables']['invoices']
    assert a['line_items'][0]['service_ref'] == b['line_items'][0]['service_ref']
    a, b = clean['tables']['invoices']
    assert a['line_items'][0]['service_ref'] != b['line_items'][0]['service_ref']
    assert len(truth['issues']) == 1 and clean_truth['issues'] == []
    validate_episode(faulty, truth)
    validate_episode(clean, clean_truth)


def test_preflight_rejects_missing_evidence_and_truth_mismatch():
    public, truth = make_episode(12)
    invalid = copy.deepcopy(truth)
    invalid['issues'][0]['allowed_evidence_sets'][0].append('made-up')
    with pytest.raises(ValueError):
        validate_episode(public, invalid)
    invalid = copy.deepcopy(truth)
    invalid['issues'][0]['expected_amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_episode(public, invalid)


def test_preflight_rejects_unbalanced_and_unreferenced_postings():
    public, truth = make_episode(12)
    invalid = copy.deepcopy(public)
    invalid['tables']['ledger'][0]['debit_minor'] += 1
    with pytest.raises(ValueError):
        validate_episode(invalid, truth)
    invalid = copy.deepcopy(public)
    invalid['tables']['ledger'][0]['invoice_id'] = 'made-up'
    with pytest.raises(ValueError):
        validate_episode(invalid, truth)
