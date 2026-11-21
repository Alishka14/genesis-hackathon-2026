"""Small FX fixture: USD and KZT both have two minor-unit decimals."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import random
from ._checks import validate_invoice_total


def _convert(amount, rate):
    return int((Decimal(amount) * Decimal(rate)).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))


def make_fx_episode(seed, mode='none'):
    if mode not in {'none', 'wrong_date', 'wrong_rate'}:
        raise ValueError('unsupported FX scenario')
    rng = random.Random(seed)
    amount = rng.randint(10000, 99999)
    episode_id = f'episode-{rng.getrandbits(48):012x}'
    entity, invoice_id, invoice_doc, payment_id, payment_doc, row1, row2, fx1, fx2 = [f'id-{rng.getrandbits(64):016x}' for _ in range(9)]
    stamp = '2026-01-10T12:00:00+00:00'
    rates = [{'rate_id': fx1, 'date': '2026-01-09', 'source_currency': 'USD', 'target_currency': 'KZT', 'rate': '440.00'}, {'rate_id': fx2, 'date': '2026-01-10', 'source_currency': 'USD', 'target_currency': 'KZT', 'rate': '450.00'}]
    used = {'none': '450.00', 'wrong_date': '440.00', 'wrong_rate': '443.00'}[mode]
    posted = _convert(amount, used)
    invoice = {'doc_id': invoice_doc, 'invoice_id': invoice_id, 'entity_id': entity, 'issued_at': stamp, 'due_at': stamp, 'currency': 'USD', 'total_minor': amount, 'line_items': [{'description': 'Synthetic immediate purchase', 'amount_minor': amount}]}
    payment = {'doc_id': payment_doc, 'payment_id': payment_id, 'timestamp': stamp, 'currency': 'USD', 'amount_minor': amount, 'invoice_refs': [{'invoice_id': invoice_id, 'amount_minor': amount}]}
    def row(row_id, account, debit, credit):
        return {'row_id': row_id, 'timestamp': stamp, 'account': account, 'debit_minor': debit, 'credit_minor': credit, 'currency': 'KZT', 'entity_id': entity, 'invoice_id': invoice_id, 'payment_id': payment_id}
    ledger = [row(row1, 'expense', posted, 0), row(row2, 'bank', 0, posted)]
    public = {'manifest': {'schema_version': '0.1', 'episode_id': episode_id, 'base_currency': 'KZT', 'period_start': '2026-01-01T00:00:00+00:00', 'period_end': '2026-01-31T23:59:59+00:00', 'timezone': '+00:00', 'rounding': 'ROUND_HALF_EVEN', 'counts': {'invoices': 1, 'ledger': 2, 'payments': 1, 'fx': 2}}, 'policy': {'fx_date': 'transaction_date', 'rounding': 'ROUND_HALF_EVEN', 'currency_exponents': {'USD': 2, 'KZT': 2}, 'fx_quote': 'target_major_per_source_major'}, 'tables': {'invoices': [invoice], 'ledger': ledger, 'payments': [payment], 'fx': rates}}
    gap = abs(_convert(amount, rates[1]['rate']) - posted)
    issues = [] if not gap else [{'issue_id': f'private-{rng.getrandbits(64):016x}', 'type': 'fx_rate_or_date', 'affected_ids': [payment_id, row1], 'expected_amount_minor': gap, 'currency': 'KZT', 'allowed_evidence_sets': [[payment_doc, invoice_doc, row1, row2, fx2]]}]
    truth = {'issues': issues}
    validate_fx_episode(public, truth)
    return public, truth


def validate_fx_episode(public, truth):
    def reject(message):
        raise ValueError(message)
    try:
        t = public['tables']
        if len(t['invoices']) != 1 or len(t['payments']) != 1 or len(t['ledger']) != 2 or len(t['fx']) != 2:
            reject('unsupported fixture shape')
        if any(public['manifest']['counts'][name] != len(t[name]) for name in t):
            reject('count mismatch')
        policy = public['policy']
        if policy['fx_date'] != 'transaction_date' or policy['rounding'] != 'ROUND_HALF_EVEN' or policy['currency_exponents'] != {'USD': 2, 'KZT': 2} or policy['fx_quote'] != 'target_major_per_source_major':
            reject('unsupported FX policy')
        inv, payment = t['invoices'][0], t['payments'][0]
        validate_invoice_total(inv)
        expense_rows = [row for row in t['ledger'] if row['account'] == 'expense']
        credit_rows = [row for row in t['ledger'] if row['account'] == 'bank']
        if len(expense_rows) != 1 or len(credit_rows) != 1:
            reject('unsupported journal accounts')
        debit, credit = expense_rows[0], credit_rows[0]
        ids = [inv['invoice_id'], inv['doc_id'], payment['payment_id'], payment['doc_id'], debit['row_id'], credit['row_id'], *[x['rate_id'] for x in t['fx']]]
        if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
            reject('non-unique or invalid IDs')
        if inv['currency'] != 'USD' or payment['currency'] != 'USD' or type(payment['amount_minor']) is not int or payment['amount_minor'] <= 0 or inv['total_minor'] != payment['amount_minor'] or payment['invoice_refs'] != [{'invoice_id': inv['invoice_id'], 'amount_minor': payment['amount_minor']}]:
            reject('invalid purchase or payment')
        for row in (debit, credit):
            if row['invoice_id'] != inv['invoice_id'] or row['payment_id'] != payment['payment_id'] or row['entity_id'] != inv['entity_id'] or row['currency'] != 'KZT' or row['timestamp'] != payment['timestamp']:
                reject('invalid journal references')
        observed = debit['debit_minor']
        if type(observed) is not int or observed <= 0 or (debit['account'], debit['credit_minor'], credit['account'], credit['debit_minor'], credit['credit_minor']) != ('expense', 0, 'bank', 0, observed):
            reject('unbalanced journal')
        dates = set()
        for rate in t['fx']:
            if rate['source_currency'] != 'USD' or rate['target_currency'] != 'KZT' or not isinstance(rate['rate'], str) or not Decimal(rate['rate']).is_finite() or Decimal(rate['rate']) <= 0 or rate['date'] in dates:
                reject('invalid or duplicate FX rate')
            dates.add(rate['date'])
        rates = [r for r in t['fx'] if r['date'] == payment['timestamp'][:10]]
        if len(rates) != 1:
            reject('no unique transaction-date rate')
        correct = _convert(payment['amount_minor'], rates[0]['rate'])
        gap = abs(correct - observed)
        issues = truth['issues']
        if len(issues) != int(gap > 0):
            reject('truth count mismatch')
        if gap:
            issue = issues[0]
            required = {payment['doc_id'], inv['doc_id'], debit['row_id'], credit['row_id'], rates[0]['rate_id']}
            if issue['type'] != 'fx_rate_or_date' or set(issue['affected_ids']) != {payment['payment_id'], debit['row_id']} or issue['expected_amount_minor'] != gap or issue['currency'] != 'KZT' or not issue['allowed_evidence_sets']:
                reject('truth differs from public calculation')
            if any(not isinstance(s, list) or not required <= set(s) or not set(s) <= set(ids) for s in issue['allowed_evidence_sets']):
                reject('incomplete or nonexistent evidence')
    except (KeyError, TypeError, IndexError, InvalidOperation) as exc:
        raise ValueError('malformed FX episode') from exc
