import copy
import pytest
from ledgergym.period_world import make_period_episode, validate_period_episode


def test_period_cutoff_uses_policy_timezone_at_boundary():
    clean, clean_truth = make_period_episode(7, fault=False)
    faulty, truth = make_period_episode(7, fault=True)
    assert clean['tables']['ledger'][0]['timestamp'] == '2026-01-31T23:30:00+00:00'
    assert clean['policy']['cutoff_timezone'] == '+05:00'
    assert clean['tables']['ledger'][0]['reporting_period'] == '2026-02'
    assert faulty['tables']['ledger'][0]['reporting_period'] == '2026-01'
    assert not clean_truth['issues']
    assert truth['issues'][0]['type'] == 'reporting_period'
    assert truth['issues'][0]['expected_amount_minor'] == faulty['tables']['invoices'][0]['total_minor']
    validate_period_episode(clean, clean_truth)
    validate_period_episode(faulty, truth)


def test_period_preflight_rejects_inconsistent_journal_and_truth():
    public, truth = make_period_episode(7, fault=True)
    broken = copy.deepcopy(public)
    broken['tables']['ledger'][1]['reporting_period'] = '2026-02'
    with pytest.raises(ValueError):
        validate_period_episode(broken, truth)
    broken_truth = copy.deepcopy(truth)
    broken_truth['issues'][0]['allowed_evidence_sets'][0].append('unknown')
    with pytest.raises(ValueError):
        validate_period_episode(public, broken_truth)


def test_period_preflight_rejects_invoice_line_item_mismatch():
    public, truth = make_period_episode(7, True)
    broken = copy.deepcopy(public)
    broken['tables']['invoices'][0]['line_items'][0]['amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_period_episode(broken, truth)


def test_period_preflight_is_invariant_to_journal_row_order():
    public, truth = make_period_episode(7, True)
    public['tables']['ledger'].reverse()
    validate_period_episode(public, truth)
