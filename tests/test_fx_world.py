import copy
from decimal import Decimal, ROUND_HALF_EVEN
import pytest
from ledgergym.fx_world import make_fx_episode, validate_fx_episode


@pytest.mark.parametrize('mode', ['none', 'wrong_date', 'wrong_rate'])
def test_fx_difference_uses_transaction_date_and_decimal(mode):
    public, truth = make_fx_episode(5, mode)
    payment = public['tables']['payments'][0]
    rate = next(r for r in public['tables']['fx'] if r['date'] == payment['timestamp'][:10])
    correct = int((Decimal(payment['amount_minor']) * Decimal(rate['rate'])).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
    observed = public['tables']['ledger'][0]['debit_minor']
    assert len(truth['issues']) == (0 if mode == 'none' else 1)
    if mode != 'none':
        assert truth['issues'][0]['expected_amount_minor'] == abs(correct - observed)
        assert truth['issues'][0]['currency'] == 'KZT'
    else:
        assert observed == correct
    validate_fx_episode(public, truth)
    assert (public, truth) == make_fx_episode(5, mode)


def test_fx_preflight_rejects_tampered_truth_and_ambiguous_rates():
    public, truth = make_fx_episode(5, 'wrong_date')
    invalid = copy.deepcopy(truth)
    invalid['issues'][0]['expected_amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_fx_episode(public, invalid)
    invalid = copy.deepcopy(public)
    invalid['tables']['fx'][1]['date'] = invalid['tables']['fx'][0]['date']
    with pytest.raises(ValueError):
        validate_fx_episode(invalid, truth)


def test_fx_preflight_rejects_invoice_line_item_mismatch():
    public, truth = make_fx_episode(5, 'wrong_date')
    broken = copy.deepcopy(public)
    broken['tables']['invoices'][0]['line_items'][0]['amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_fx_episode(broken, truth)


def test_fx_preflight_is_invariant_to_journal_row_order():
    public, truth = make_fx_episode(5, 'wrong_rate')
    public['tables']['ledger'].reverse()
    public['tables']['fx'].reverse()
    validate_fx_episode(public, truth)
