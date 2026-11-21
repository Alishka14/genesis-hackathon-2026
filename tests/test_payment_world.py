import copy
import pytest
from ledgergym.payment_world import make_payment_episode, validate_payment_episode


@pytest.mark.parametrize('mode,ratio', [('none', 0), ('missing', 1), ('partial', .5)])
def test_payment_allocation_is_derivable_from_public_records(mode, ratio):
    public, truth = make_payment_episode(17, mode)
    invoice = public['tables']['invoices'][0]
    payment = public['tables']['payments'][0]
    amount = payment['amount_minor']
    allocated = sum(item['amount_minor'] for item in payment['invoice_refs'])
    assert payment['remittance_invoice_id'] == invoice['invoice_id']
    assert allocated == amount - int(amount * ratio)
    assert len(truth['issues']) == (0 if mode == 'none' else 1)
    if mode != 'none':
        issue = truth['issues'][0]
        assert issue['type'] == 'payment_allocation'
        assert set(issue['affected_ids']) == {invoice['invoice_id'], payment['payment_id']}
        assert issue['expected_amount_minor'] == amount - allocated
        assert {invoice['doc_id'], payment['doc_id']} <= set(issue['allowed_evidence_sets'][0])
    validate_payment_episode(public, truth)
    assert (public, truth) == make_payment_episode(17, mode)


def test_payment_preflight_rejects_fabrication_and_overallocation():
    public, truth = make_payment_episode(17, 'partial')
    invalid = copy.deepcopy(public)
    invalid['tables']['payments'][0]['invoice_refs'][0]['amount_minor'] = 999999999
    with pytest.raises(ValueError):
        validate_payment_episode(invalid, truth)
    invalid_truth = copy.deepcopy(truth)
    invalid_truth['issues'][0]['allowed_evidence_sets'][0].append('missing-doc')
    with pytest.raises(ValueError):
        validate_payment_episode(public, invalid_truth)


def test_payment_episode_runs_through_environment_and_evaluator():
    from ledgergym.env import LedgerSandbox
    from ledgergym.score import evaluate
    public, truth = make_payment_episode(33, 'partial')
    public_ids = {v for table in public['tables'].values() for row in table for k, v in row.items() if k.endswith('_id') and isinstance(v, str)}
    env = LedgerSandbox(public, lambda findings, steps: evaluate(truth['issues'], findings, public_ids, steps))
    env.reset()
    payment_result, _, _, _, _ = env.step({'action': 'list_records', 'table': 'payments', 'limit': 50})
    payment = payment_result['records'][0]
    assert payment['amount_minor'] > sum(x['amount_minor'] for x in payment['invoice_refs'])
    issue = truth['issues'][0]
    finding = {'type': issue['type'], 'affected_ids': issue['affected_ids'], 'claimed_amount_minor': issue['expected_amount_minor'], 'currency': issue['currency'], 'evidence_ids': issue['allowed_evidence_sets'][0], 'explanation': ''}
    _, reward, terminated, truncated, info = env.step({'action': 'submit', 'episode_id': public['manifest']['episode_id'], 'findings': [finding]})
    assert terminated and not truncated and info['score']['tp'] == 1 and reward == .998


def test_payment_preflight_rejects_invoice_line_item_mismatch():
    public, truth = make_payment_episode(17, 'partial')
    broken = copy.deepcopy(public)
    broken['tables']['invoices'][0]['line_items'][0]['amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_payment_episode(broken, truth)
