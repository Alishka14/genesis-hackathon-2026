"""Trusted offline baselines for small public fixtures; NOT an isolation boundary."""
import copy
import random
from .env import LedgerSandbox
from .fx_world import _convert
from .period_world import _period
from .score import evaluate, accessible_evidence_ids


def _finding(kind, affected, amount, currency, evidence):
    return {'type': kind, 'affected_ids': affected, 'claimed_amount_minor': amount, 'currency': currency, 'evidence_ids': list(dict.fromkeys(evidence)), 'explanation': ''}


def _reconcile(tables, policy):
    """Simple rules for current fixtures; not a general financial auditor."""
    invoices, rows, payments, rates = (tables[k] for k in ('invoices', 'ledger', 'payments', 'fx'))
    by_invoice = {x['invoice_id']: x for x in invoices}
    findings = []
    if policy.get('duplicate_rule') == 'one_invoice_per_service_ref':
        groups = {}
        for invoice in invoices:
            for line in invoice.get('line_items', []):
                if 'service_ref' in line:
                    groups.setdefault((invoice['entity_id'], line['service_ref']), []).append(invoice)
        for group in groups.values():
            if len(group) == 2 and group[0]['currency'] == group[1]['currency'] and group[0]['total_minor'] == group[1]['total_minor']:
                ids = [i['invoice_id'] for i in group]
                evidence_rows = [r['row_id'] for r in rows if r['invoice_id'] in ids and r['account'] == 'expense']
                if len(evidence_rows) == 2:
                    findings.append(_finding('duplicate_invoice', ids, group[1]['total_minor'], group[1]['currency'], [i['doc_id'] for i in group] + evidence_rows))
    for payment in payments:
        date = payment['timestamp'][:10]
        rate = next((r for r in rates if r['date'] == date and r['source_currency'] == payment['currency'] and r['target_currency'] == 'KZT'), None)
        payment_rows = [r for r in rows if r['payment_id'] == payment['payment_id']]
        debit = next((r for r in payment_rows if r['account'] == 'expense'), None)
        if rate and debit:
            invoice = by_invoice.get(debit['invoice_id'])
            gap = abs(_convert(payment['amount_minor'], rate['rate']) - debit['debit_minor'])
            if gap and invoice and len(payment_rows) == 2:
                findings.append(_finding('fx_rate_or_date', [payment['payment_id'], debit['row_id']], gap, 'KZT', [payment['doc_id'], invoice['doc_id']] + [r['row_id'] for r in payment_rows] + [rate['rate_id']]))
        if policy.get('allocation_rule') == 'allocate_full_payment_to_remittance_invoice':
            target = by_invoice.get(payment.get('remittance_invoice_id'))
            if not target:
                continue
            allocations = payment.get('invoice_refs', [])
            allocated = sum(a['amount_minor'] for a in allocations if a['invoice_id'] == target['invoice_id'])
            gap = payment['amount_minor'] - allocated
            if gap > 0:
                amount, currency = gap, payment['currency']
                evidence = [target['doc_id'], payment['doc_id']] + [r['row_id'] for r in payment_rows]
                for a in allocations:
                    if a['invoice_id'] != target['invoice_id'] and a['invoice_id'] in by_invoice:
                        evidence.append(by_invoice[a['invoice_id']]['doc_id'])
                if policy.get('allocation_claim_currency') == 'KZT' and rate:
                    amount, currency = _convert(gap, rate['rate']), 'KZT'
                    evidence.append(rate['rate_id'])
                findings.append(_finding('payment_allocation', [target['invoice_id'], payment['payment_id']], amount, currency, evidence))
    if policy.get('period_rule') == 'calendar_month_of_transaction':
        for invoice in invoices:
            journal = [r for r in rows if r['invoice_id'] == invoice['invoice_id']]
            if len(journal) == 2 and all('reporting_period' in r for r in journal):
                expected = _period(invoice['issued_at'], policy['cutoff_timezone'])
                if any(r['reporting_period'] != expected for r in journal):
                    findings.append(_finding('reporting_period', [r['row_id'] for r in journal], invoice['total_minor'], invoice['currency'], [invoice['doc_id']] + [r['row_id'] for r in journal]))
    return findings[:30]


def run_baseline(public, truth, policy, seed=0):
    """Run only trusted in-process fixture baselines; do not expose to agents.

    The oracle directly consumes truth and returns no trajectory. Other policies
    see only public reset/list results. The caller remains responsible for OS
    isolation and for protecting truth, seed and evaluator outputs.
    """
    if policy not in {'oracle', 'seeded_random', 'mark_all', 'reconciliation'}:
        raise ValueError('unknown baseline')
    # Use the same addressable evidence IDs as the canonical evaluator.
    # Entity or relationship keys alone are not retrievable proof documents.
    public_ids = accessible_evidence_ids(public)
    if policy == 'oracle':
        findings = [_finding(i['type'], i['affected_ids'], i['expected_amount_minor'], i['currency'], i['allowed_evidence_sets'][0]) for i in truth['issues']]
        return {'score': evaluate(truth['issues'], findings, public_ids, 0), 'trajectory': None}
    env = LedgerSandbox(public, lambda answers, steps: evaluate(truth['issues'], answers, public_ids, steps))
    initial, _ = env.reset()
    tables = {k: [] for k in ('invoices', 'payments', 'ledger', 'fx')}
    trajectory = []
    budget_exhausted = False
    for name in tables:
        cursor = None
        cursor_step = None
        while True:
            if len(trajectory) >= 99:
                budget_exhausted = True
                break
            action = {'action': 'list_records', 'table': name, 'limit': 50}
            if cursor is not None:
                action['cursor'] = cursor
            obs, _, terminated, truncated, _ = env.step(action)
            recorded = copy.deepcopy(action)
            if cursor is not None:
                recorded['cursor'] = {'from_step': cursor_step}
            trajectory.append(recorded)
            if terminated or truncated or 'records' not in obs:
                raise ValueError('cannot inspect fixture')
            tables[name].extend(obs['records'])
            cursor = obs['next_cursor']
            cursor_step = len(trajectory) - 1
            if cursor is None:
                break
        if budget_exhausted:
            break
    invoices = tables['invoices']
    if policy == 'reconciliation':
        model = initial['policy'].get('accounting_model')
        if model == 'accrual_company_v1':
            from .company_checks import inspect_company
            findings = inspect_company({'manifest': initial['manifest'], 'policy': initial['policy'], 'tables': tables})
        elif model == 'accrual_company_v2':
            from .company_checks_v2 import validate_settlement_company
            # Validate each public documentary and journal fact independently.
            # This is a clean-only model: no private truth is consulted here.
            validate_settlement_company(
                {'manifest': initial['manifest'], 'policy': initial['policy'], 'tables': tables},
                {'issues': []})
            findings = []
        else:
            findings = _reconcile(tables, initial['policy'])
    elif policy == 'mark_all':
        findings = [_finding(kind, [i['invoice_id']], i['total_minor'], i['currency'], [i['doc_id']]) for i in invoices for kind in ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')][:30]
    elif invoices:
        rng = random.Random(seed)
        inv = rng.choice(invoices)
        findings = [_finding(rng.choice(['duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period']), [inv['invoice_id']], inv['total_minor'], inv['currency'], [inv['doc_id']])]
    else:
        findings = []
    submission = {'action': 'submit', 'episode_id': initial['manifest']['episode_id'], 'findings': findings}
    _, _, terminated, truncated, info = env.step(submission)
    trajectory.append(copy.deepcopy(submission))
    if not terminated or truncated or 'score' not in info:
        raise ValueError('baseline submit failed')
    return {'score': info['score'], 'trajectory': trajectory}
