"""Small linked scenarios, not claims of full contest coverage."""
import copy
from decimal import Decimal
import pytest
from ledgergym.generator import generate_episode
from ledgergym.compound_world import validate_compound


@pytest.mark.parametrize('scenario,types', [
    ('fx_allocation', {'fx_rate_or_date', 'payment_allocation'}),
    ('duplicate_allocation', {'duplicate_invoice', 'payment_allocation'}),
])
def test_compound_has_two_faults_on_shared_payment_or_invoice(scenario, types):
    public, truth = generate_episode(17, {'scenario': scenario})
    assert {i['type'] for i in truth['issues']} == types
    assert len(truth['issues']) == 2
    payment = public['tables']['payments'][0]
    assert all(payment['doc_id'] in issue['allowed_evidence_sets'][0] or (scenario == 'duplicate_allocation' and issue['type'] == 'duplicate_invoice') for issue in truth['issues'])
    validate_compound(public, truth)
    assert (public, truth) == generate_episode(17, {'scenario': scenario})
    if scenario == 'fx_allocation':
        correct_rate = next(r for r in public['tables']['fx'] if r['date'] == payment['timestamp'][:10])
        allocation = next(i for i in truth['issues'] if i['type'] == 'payment_allocation')
        gap = payment['amount_minor'] - payment['invoice_refs'][0]['amount_minor']
        assert allocation['currency'] == 'KZT'
        assert allocation['expected_amount_minor'] == int(Decimal(gap) * Decimal(correct_rate['rate']))
        assert correct_rate['rate_id'] in allocation['allowed_evidence_sets'][0]
    else:
        duplicate = next(i for i in truth['issues'] if i['type'] == 'duplicate_invoice')
        allocated = payment['invoice_refs'][0]['invoice_id']
        assert allocated in duplicate['affected_ids'] and allocated != payment['remittance_invoice_id']


@pytest.mark.parametrize('scenario', ['fx_allocation', 'duplicate_allocation'])
@pytest.mark.parametrize('first,allocation', [(False,False),(True,False),(False,True),(True,True)])
def test_compound_switches_control_two_issues_independently(scenario, first, allocation):
    public, truth = generate_episode(9, {'scenario': scenario, 'first_fault': first, 'allocation_fault': allocation})
    validate_compound(public, truth)
    assert len(truth['issues']) == int(first) + int(allocation)
    assert (any(i['type'] == 'payment_allocation' for i in truth['issues'])) == allocation


@pytest.mark.parametrize('scenario', ['fx_allocation', 'duplicate_allocation'])
def test_compound_preflight_rejects_tampered_hidden_answer(scenario):
    public, truth = generate_episode(12, {'scenario': scenario})
    broken = copy.deepcopy(truth)
    broken['issues'][0]['expected_amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_compound(public, broken)


@pytest.mark.parametrize('scenario', ['fx_allocation', 'duplicate_allocation'])
def test_compound_files_round_trip_and_score_through_environment(tmp_path, scenario):
    from ledgergym.episode_io import export_episode, load_public_episode
    from ledgergym.env import LedgerSandbox
    from ledgergym.score import evaluate
    public, truth = generate_episode(34, {'scenario': scenario})
    export_episode(tmp_path / 'episode', public, truth, seed=34)
    loaded = load_public_episode(tmp_path / 'episode' / 'public')
    assert loaded == public
    public_ids = {v for rows in loaded['tables'].values() for row in rows for key, v in row.items() if key.endswith('_id') and isinstance(v, str)}
    findings = [{'type': i['type'], 'affected_ids': i['affected_ids'], 'claimed_amount_minor': i['expected_amount_minor'], 'currency': i['currency'], 'evidence_ids': i['allowed_evidence_sets'][0], 'explanation': ''} for i in truth['issues']]
    env = LedgerSandbox(loaded, lambda answers, steps: evaluate(truth['issues'], answers, public_ids, steps))
    env.reset()
    env.step({'action': 'list_records', 'table': 'payments', 'limit': 50})
    _, reward, terminated, truncated, info = env.step({'action': 'submit', 'episode_id': loaded['manifest']['episode_id'], 'findings': findings})
    assert terminated and not truncated and reward == .998 and info['score']['tp'] == 2


@pytest.mark.parametrize('scenario', ['fx_allocation', 'duplicate_allocation'])
def test_compound_answers_independently_derived_from_public_records(scenario):
    from ledgergym.score import evaluate
    public, truth = generate_episode(34, {'scenario': scenario})
    tables = public['tables']
    payment = tables['payments'][0]
    invoice = next(x for x in tables['invoices'] if x['invoice_id'] == payment['remittance_invoice_id'])
    rows = tables['ledger']
    if scenario == 'fx_allocation':
        rate = next(x for x in tables['fx'] if x['date'] == payment['timestamp'][:10])
        debit = next(x for x in rows if x['account'] == 'expense')
        credit = next(x for x in rows if x['account'] == 'bank')
        expected = int(Decimal(payment['amount_minor']) * Decimal(rate['rate']))
        gap = payment['amount_minor'] - payment['invoice_refs'][0]['amount_minor']
        findings = [
            {'type': 'fx_rate_or_date', 'affected_ids': [payment['payment_id'], debit['row_id']], 'claimed_amount_minor': abs(expected - debit['debit_minor']), 'currency': 'KZT', 'evidence_ids': [payment['doc_id'], invoice['doc_id'], debit['row_id'], credit['row_id'], rate['rate_id']], 'explanation': ''},
            {'type': 'payment_allocation', 'affected_ids': [invoice['invoice_id'], payment['payment_id']], 'claimed_amount_minor': int(Decimal(gap) * Decimal(rate['rate'])), 'currency': 'KZT', 'evidence_ids': [payment['doc_id'], invoice['doc_id'], debit['row_id'], credit['row_id'], rate['rate_id']], 'explanation': ''},
        ]
    else:
        other = next(x for x in tables['invoices'] if x['invoice_id'] != invoice['invoice_id'])
        assert invoice['line_items'][0]['service_ref'] == other['line_items'][0]['service_ref']
        assert payment['invoice_refs'][0]['invoice_id'] == other['invoice_id']
        invoice_rows = [r['row_id'] for r in rows if r['account'] == 'expense']
        payment_rows = [r['row_id'] for r in rows if r['payment_id'] == payment['payment_id']]
        findings = [
            {'type': 'duplicate_invoice', 'affected_ids': [invoice['invoice_id'], other['invoice_id']], 'claimed_amount_minor': other['total_minor'], 'currency': 'KZT', 'evidence_ids': [invoice['doc_id'], other['doc_id'], *invoice_rows], 'explanation': ''},
            {'type': 'payment_allocation', 'affected_ids': [invoice['invoice_id'], payment['payment_id']], 'claimed_amount_minor': payment['amount_minor'], 'currency': 'KZT', 'evidence_ids': [invoice['doc_id'], other['doc_id'], payment['doc_id'], *payment_rows], 'explanation': ''},
        ]
    public_ids = {v for rows in tables.values() for row in rows for key, v in row.items() if key.endswith('_id') and isinstance(v, str)}
    result = evaluate(truth['issues'], findings, public_ids, 0)
    assert (result['tp'], result['fp'], result['fn']) == (2, 0, 0)
    incomplete = copy.deepcopy(findings)
    incomplete[1]['evidence_ids'].pop()
    result = evaluate(truth['issues'], incomplete, public_ids, 0)
    assert (result['tp'], result['fp'], result['fn']) == (1, 1, 1)


def test_fx_allocation_preflight_rejects_missing_exchange_evidence():
    public, truth = generate_episode(10, {'scenario': 'fx_allocation'})
    broken = copy.deepcopy(truth)
    rate_id = next(r['rate_id'] for r in public['tables']['fx'] if r['date'] == public['tables']['payments'][0]['timestamp'][:10])
    issue = next(i for i in broken['issues'] if i['type'] == 'payment_allocation')
    issue['allowed_evidence_sets'][0].remove(rate_id)
    with pytest.raises(ValueError):
        validate_compound(public, broken)


def test_duplicate_allocation_preflight_rejects_unknown_remittance():
    public, truth = generate_episode(10, {'scenario': 'duplicate_allocation'})
    broken = copy.deepcopy(public)
    broken['tables']['payments'][0]['remittance_invoice_id'] = 'unknown'
    with pytest.raises(ValueError):
        validate_compound(broken, truth)
