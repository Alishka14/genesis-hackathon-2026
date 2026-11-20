"""Deterministic reporting-period fixture with a timezone-boundary event."""
from datetime import datetime, timedelta, timezone
import random
from ._checks import validate_invoice_total
import re


def _period(timestamp, offset):
    if not isinstance(offset, str) or not re.fullmatch(r'[+-](?:0\d|1[0-4]):[0-5]\d', offset):
        raise ValueError('invalid offset')
    hours, minutes = map(int, offset[1:].split(':'))
    if hours == 14 and minutes:
        raise ValueError('invalid offset')
    delta = timedelta(hours=hours, minutes=minutes) * (1 if offset[0] == '+' else -1)
    value = datetime.fromisoformat(timestamp)
    if value.utcoffset() is None:
        raise ValueError('timestamp needs offset')
    return value.astimezone(timezone(delta)).strftime('%Y-%m')


def make_period_episode(seed, fault=False):
    if not isinstance(fault, bool):
        raise ValueError('fault must be a bool')
    rng = random.Random(seed)
    amount = rng.randint(10000, 99999)
    episode_id = f'episode-{rng.getrandbits(48):012x}'
    entity, invoice_id, invoice_doc, row1, row2 = [f'id-{rng.getrandbits(64):016x}' for _ in range(5)]
    stamp = '2026-01-31T23:30:00+00:00'
    period = '2026-01' if fault else '2026-02'
    invoice = {'doc_id': invoice_doc, 'invoice_id': invoice_id, 'entity_id': entity, 'issued_at': stamp, 'due_at': '2026-02-28T23:59:59+05:00', 'currency': 'KZT', 'total_minor': amount, 'line_items': [{'description': 'Synthetic service', 'amount_minor': amount}]}
    def row(row_id, account, debit, credit):
        return {'row_id': row_id, 'timestamp': stamp, 'account': account, 'debit_minor': debit, 'credit_minor': credit, 'currency': 'KZT', 'entity_id': entity, 'invoice_id': invoice_id, 'payment_id': None, 'reporting_period': period}
    ledger = [row(row1, 'expense', amount, 0), row(row2, 'payable', 0, amount)]
    public = {'manifest': {'schema_version': '0.1', 'episode_id': episode_id, 'base_currency': 'KZT', 'period_start': '2026-02-01T00:00:00+05:00', 'period_end': '2026-02-28T23:59:59+05:00', 'timezone': '+05:00', 'rounding': 'ROUND_HALF_EVEN', 'counts': {'invoices': 1, 'ledger': 2, 'payments': 0, 'fx': 0}}, 'policy': {'cutoff_timezone': '+05:00', 'period_rule': 'calendar_month_of_transaction', 'rounding': 'ROUND_HALF_EVEN', 'fx_date': 'transaction_date'}, 'tables': {'invoices': [invoice], 'ledger': ledger, 'payments': [], 'fx': []}}
    issues = [] if not fault else [{'issue_id': f'private-{rng.getrandbits(64):016x}', 'type': 'reporting_period', 'affected_ids': [row1, row2], 'expected_amount_minor': amount, 'currency': 'KZT', 'allowed_evidence_sets': [[invoice_doc, row1, row2]]}]
    truth = {'issues': issues}
    validate_period_episode(public, truth)
    return public, truth


def validate_period_episode(public, truth):
    def reject(reason):
        raise ValueError(reason)
    try:
        tables = public['tables']
        if len(tables['invoices']) != 1 or len(tables['ledger']) != 2 or tables['payments'] or tables['fx']:
            reject('unsupported fixture shape')
        if any(public['manifest']['counts'][name] != len(tables[name]) for name in tables):
            reject('count mismatch')
        if public['policy']['period_rule'] != 'calendar_month_of_transaction':
            reject('unsupported period policy')
        invoice = tables['invoices'][0]
        validate_invoice_total(invoice)
        expense_rows = [row for row in tables['ledger'] if row['account'] == 'expense']
        credit_rows = [row for row in tables['ledger'] if row['account'] == 'payable']
        if len(expense_rows) != 1 or len(credit_rows) != 1:
            reject('unsupported journal accounts')
        debit, credit = expense_rows[0], credit_rows[0]
        ids = [invoice['invoice_id'], invoice['doc_id'], debit['row_id'], credit['row_id']]
        if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
            reject('invalid or duplicate IDs')
        amount = invoice['total_minor']
        if type(amount) is not int or amount <= 0:
            reject('invalid amount')
        for row in (debit, credit):
            if row['invoice_id'] != invoice['invoice_id'] or row['payment_id'] is not None or row['entity_id'] != invoice['entity_id'] or row['currency'] != invoice['currency'] or row['timestamp'] != invoice['issued_at']:
                reject('journal reference mismatch')
        if (debit['account'], debit['debit_minor'], debit['credit_minor'], credit['account'], credit['debit_minor'], credit['credit_minor']) != ('expense', amount, 0, 'payable', 0, amount):
            reject('unbalanced journal')
        if debit['reporting_period'] != credit['reporting_period']:
            reject('inconsistent journal periods')
        expected_period = _period(invoice['issued_at'], public['policy']['cutoff_timezone'])
        manifest = public['manifest']
        if _period(manifest['period_start'], public['policy']['cutoff_timezone']) != expected_period or _period(manifest['period_end'], public['policy']['cutoff_timezone']) != expected_period:
            reject('event outside manifest month')
        fault = debit['reporting_period'] != expected_period
        issues = truth['issues']
        if len(issues) != int(fault):
            reject('truth count mismatch')
        if fault:
            issue = issues[0]
            required = {invoice['doc_id'], debit['row_id'], credit['row_id']}
            if issue['type'] != 'reporting_period' or set(issue['affected_ids']) != {debit['row_id'], credit['row_id']} or issue['expected_amount_minor'] != amount or issue['currency'] != invoice['currency'] or not issue['allowed_evidence_sets']:
                reject('truth does not match period')
            if any(not isinstance(s, list) or not required <= set(s) or not set(s) <= set(ids) for s in issue['allowed_evidence_sets']):
                reject('invalid or incomplete evidence')
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('malformed period episode') from exc
