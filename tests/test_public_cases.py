"""Cross-module checks calculate findings only from public fixture fields."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import pytest
from ledgergym.env import LedgerSandbox
from ledgergym.fx_world import make_fx_episode
from ledgergym.payment_world import make_payment_episode
from ledgergym.period_world import make_period_episode
from ledgergym.score import evaluate
from ledgergym.world import make_episode


def derive(public, kind):
    tables = public['tables']
    invoices, ledger = tables['invoices'], tables['ledger']
    if kind == 'duplicate_invoice':
        a, b = invoices
        if a['line_items'][0]['service_ref'] != b['line_items'][0]['service_ref']:
            return []
        return [{'type': kind, 'affected_ids': [a['invoice_id'], b['invoice_id']], 'claimed_amount_minor': b['total_minor'], 'currency': b['currency'], 'evidence_ids': [a['doc_id'], b['doc_id'], *[r['row_id'] for r in ledger if r['account'] == 'expense']], 'explanation': ''}]
    if kind == 'payment_allocation':
        p, i = tables['payments'][0], invoices[0]
        gap = p['amount_minor'] - sum(x['amount_minor'] for x in p['invoice_refs'])
        if not gap:
            return []
        return [{'type': kind, 'affected_ids': [i['invoice_id'], p['payment_id']], 'claimed_amount_minor': gap, 'currency': p['currency'], 'evidence_ids': [i['doc_id'], p['doc_id'], *[r['row_id'] for r in ledger if r['payment_id'] == p['payment_id']]], 'explanation': ''}]
    if kind == 'fx_rate_or_date':
        p, i = tables['payments'][0], invoices[0]
        rate = next(r for r in tables['fx'] if r['date'] == p['timestamp'][:10])
        expected = int((Decimal(p['amount_minor']) * Decimal(rate['rate'])).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
        gap = abs(expected - ledger[0]['debit_minor'])
        if not gap:
            return []
        return [{'type': kind, 'affected_ids': [p['payment_id'], ledger[0]['row_id']], 'claimed_amount_minor': gap, 'currency': ledger[0]['currency'], 'evidence_ids': [p['doc_id'], i['doc_id'], *[r['row_id'] for r in ledger], rate['rate_id']], 'explanation': ''}]
    i = invoices[0]
    offset = public['policy']['cutoff_timezone']
    minutes = (int(offset[1:3]) * 60 + int(offset[4:])) * (1 if offset[0] == '+' else -1)
    period = datetime.fromisoformat(i['issued_at']).astimezone(timezone(timedelta(minutes=minutes))).strftime('%Y-%m')
    if period == ledger[0]['reporting_period']:
        return []
    return [{'type': kind, 'affected_ids': [r['row_id'] for r in ledger], 'claimed_amount_minor': i['total_minor'], 'currency': i['currency'], 'evidence_ids': [i['doc_id'], *[r['row_id'] for r in ledger]], 'explanation': ''}]


@pytest.mark.parametrize('kind,factory', [
    ('duplicate_invoice', lambda fault: make_episode(13, fault)),
    ('payment_allocation', lambda fault: make_payment_episode(13, 'partial' if fault else 'none')),
    ('fx_rate_or_date', lambda fault: make_fx_episode(13, 'wrong_date' if fault else 'none')),
    ('reporting_period', lambda fault: make_period_episode(13, fault)),
])
@pytest.mark.parametrize('fault', [False, True])
def test_public_derivation_scores_through_environment(kind, factory, fault):
    public, truth = factory(fault)
    findings = derive(public, kind)
    assert len(findings) == int(fault)
    ids = {v for rows in public['tables'].values() for row in rows for k, v in row.items() if k.endswith('_id') and isinstance(v, str)}
    env = LedgerSandbox(public, lambda answers, steps: evaluate(truth['issues'], answers, ids, steps))
    env.reset()
    for table in public['tables']:
        obs, reward, terminated, truncated, _ = env.step({'action': 'list_records', 'table': table, 'limit': 50})
        assert reward == 0 and not terminated and not truncated and 'records' in obs
    _, reward, terminated, truncated, info = env.step({'action': 'submit', 'episode_id': public['manifest']['episode_id'], 'findings': findings})
    assert terminated and not truncated and info['score']['f1'] == 1.0 and reward == .992
