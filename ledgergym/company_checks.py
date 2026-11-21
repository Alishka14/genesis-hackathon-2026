"""Public-only checks for the provisional accrual company model.

Uses rational arithmetic independently of the generator's Decimal conversion.
The reconciliation baseline shares these rules, so it is not independent QA.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import re


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive(value):
    return type(value) is int and value > 0


def _local_moment(value, zone=timezone(timedelta(hours=5))):
    stamp = datetime.fromisoformat(value)
    _require(stamp.utcoffset() is not None, 'timestamp needs offset')
    return stamp.astimezone(zone)


def _rounded(amount, rate):
    value = amount * Fraction(rate)
    whole, remainder = divmod(value.numerator, value.denominator)
    return whole + int(2 * remainder > value.denominator or
                       (2 * remainder == value.denominator and whole % 2 == 1))


def _finding(kind, affected, amount, currency, evidence):
    return {'type': kind, 'affected_ids': sorted(affected), 'claimed_amount_minor': amount,
            'currency': currency, 'evidence_ids': sorted(set(evidence)), 'explanation': ''}


def inspect_company(public):
    """Validate the supported model and derive findings without private truth.

    Checks financial consistency at any size; generator config enforces dataset
    size limits. Unsupported corruption raises ValueError instead of becoming a
    new labelled fault. Only invoice period, duplicate identity, allocation and
    payment FX deviations are supported.
    """
    try:
        return _inspect(public)
    except (KeyError, TypeError, IndexError, StopIteration, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('malformed company episode') from exc


def _inspect(public):
    manifest, policy, tables = public['manifest'], public['policy'], public['tables']
    _require(manifest['schema_version'] == '0.3-company' and manifest['base_currency'] == 'KZT', 'unsupported company schema')
    # Deliberately bounded, explicit variants. Never accept an unknown FX basis
    # or infer currency exponents from untrusted values.
    zone_text = policy.get('cutoff_timezone')
    _require(zone_text in ('+03:00', '+05:00', '+09:00'), 'unsupported cutoff timezone')
    zone = timezone(timedelta(hours=int(zone_text[1:3])))
    foreign = next((name for name in ('USD', 'EUR')
                    if policy.get('currency_exponents') == {'KZT': 2, name: 2}), None)
    _require(foreign is not None, 'unsupported FX currency or exponent')
    def _moment(value):
        return _local_moment(value, zone)
    required_policy = {'accounting_model': 'accrual_company_v1', 'rounding': 'ROUND_HALF_EVEN',
                       'currency_exponents': {'KZT': 2, foreign: 2}, 'fx_date': 'local_transaction_date',
                       'cutoff_timezone': zone_text, 'period_rule': 'calendar_month_of_transaction',
                       'invoice_rounding': 'round_total_residual_to_last_line',
                       'duplicate_rule': 'one_invoice_per_service_ref',
                       'allocation_rule': 'allocate_full_payment_to_remittance_invoice',
                       'allocation_claim_currency': 'KZT'}
    _require(all(policy.get(k) == v for k, v in required_policy.items()), 'unsupported company policy')
    _require(manifest['timezone'] == zone_text and manifest['rounding'] == 'ROUND_HALF_EVEN', 'manifest policy mismatch')
    _require(set(tables) == {'ledger', 'invoices', 'payments', 'fx'}, 'unexpected tables')
    _require(manifest['counts'] == {k: len(v) for k, v in tables.items()}, 'count mismatch')
    start, end = _moment(manifest['period_start']), _moment(manifest['period_end'])
    _require(start <= end and start.strftime('%Y-%m') == end.strftime('%Y-%m'), 'invalid period')
    ids = set()
    def register(value):
        _require(isinstance(value, str) and 0 < len(value) <= 128 and value not in ids, 'invalid or repeated ID')
        ids.add(value)
    for table, key in [('invoices', 'invoice_id'), ('payments', 'payment_id'), ('ledger', 'row_id'), ('fx', 'rate_id')]:
        for record in tables[table]:
            register(record[key])
            if table in ('invoices', 'payments'):
                register(record['doc_id'])
    rates, by_rate = {}, {}
    for rate in tables['fx']:
        _require(rate['source_currency'] == foreign and rate['target_currency'] == 'KZT', 'unsupported currency quote')
        _require(isinstance(rate['rate'], str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', rate['rate']) is not None
                 and Fraction(rate['rate']) > 0, 'invalid FX rate')
        _require(rate['date'] not in rates and datetime.fromisoformat(rate['date']).date().isoformat() == rate['date'], 'duplicate or invalid rate date')
        rates[rate['date']], by_rate[rate['rate_id']] = rate, rate
    def correct_rate(currency, stamp):
        if currency == 'KZT':
            return '1', None
        _require(currency == foreign, 'unsupported document currency')
        rate = rates[_moment(stamp).date().isoformat()]
        return rate['rate'], rate['rate_id']
    invoices = {i['invoice_id']: i for i in tables['invoices']}
    payments = {p['payment_id']: p for p in tables['payments']}
    invoice_rows, payment_rows, opening = defaultdict(list), defaultdict(list), []
    for row in tables['ledger']:
        _require(type(row['debit_minor']) is int and type(row['credit_minor']) is int and
                 row['debit_minor'] >= 0 and row['credit_minor'] >= 0 and
                 (row['debit_minor'] > 0) != (row['credit_minor'] > 0), 'invalid posting money')
        _require(row['currency'] == 'KZT', 'wrong journal currency')
        _require(start <= _moment(row['timestamp']) <= end, 'posting outside period window')
        _require(isinstance(row['reporting_period'], str) and re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', row['reporting_period']), 'invalid reporting period')
        if row['payment_id'] is not None:
            _require(row['payment_id'] in payments and row['invoice_id'] in invoices, 'orphan payment row')
            payment_rows[row['payment_id']].append(row)
        elif row['invoice_id'] is not None:
            _require(row['invoice_id'] in invoices, 'orphan invoice row')
            invoice_rows[row['invoice_id']].append(row)
        else:
            opening.append(row)
    findings, identities, credits = [], defaultdict(list), {}
    for invoice in invoices.values():
        invoice_id, lines = invoice['invoice_id'], invoice['line_items']
        _require(_positive(invoice['total_minor']) and isinstance(lines, list) and lines, 'invalid invoice')
        _require(start <= _moment(invoice['issued_at']) <= end and _moment(invoice['due_at']) >= _moment(invoice['issued_at']), 'invalid invoice dates')
        _require(isinstance(invoice['entity_id'], str) and invoice['entity_id'], 'invalid supplier')
        for line in lines:
            register(line['line_id'])
            _require(_positive(line['amount_minor']) and isinstance(line['service_ref'], str) and line['service_ref'], 'invalid service component')
        _require(sum(line['amount_minor'] for line in lines) == invoice['total_minor'], 'invoice total differs from components')
        services = {line['service_ref'] for line in lines}
        _require(len(services) == 1, 'one business identity required per invoice')
        identities[(invoice['entity_id'], next(iter(services)))].append(invoice)
        rate, rate_id = correct_rate(invoice['currency'], invoice['issued_at'])
        total = _rounded(invoice['total_minor'], rate)
        expected = [_rounded(line['amount_minor'], rate) for line in lines[:-1]]
        expected.append(total - sum(expected))
        _require(all(amount > 0 for amount in expected), 'nonpositive converted component')
        rows = invoice_rows[invoice_id]
        _require(len(rows) == len(lines) + 1, 'invoice postings incomplete')
        debit = {r['line_id']: r for r in rows if r['account'] == 'expense'}
        credit = [r for r in rows if r['account'] == 'payable']
        _require(len(debit) == len(lines) and len(credit) == 1, 'invalid invoice accounts')
        credit = credit[0]
        credits[invoice_id] = credit
        _require(credit['line_id'] is None and credit['credit_minor'] == total and credit['debit_minor'] == 0, 'invoice credit differs from source')
        for line, amount in zip(lines, expected):
            row = debit[line['line_id']]
            _require(row['debit_minor'] == amount and row['credit_minor'] == 0, 'component posting differs from source')
        _require(all(r['entity_id'] == invoice['entity_id'] and _moment(r['timestamp']) == _moment(invoice['issued_at'])
                     and r['rate_id'] == rate_id for r in rows), 'invoice posting scope or FX mismatch')
        periods = {r['reporting_period'] for r in rows}
        _require(len(periods) == 1, 'inconsistent invoice reporting periods')
        if next(iter(periods)) != _moment(invoice['issued_at']).strftime('%Y-%m'):
            findings.append(_finding('reporting_period', [invoice_id], total, 'KZT', [invoice['doc_id'], credit['row_id']]))
    for group in identities.values():
        _require(len(group) <= 2, 'unsupported repeated obligation count')
        if len(group) == 2:
            first, second = group
            _require(first['currency'] == second['currency'] and first['total_minor'] == second['total_minor'], 'ambiguous duplicate value')
            findings.append(_finding('duplicate_invoice', [i['invoice_id'] for i in group], first['total_minor'], first['currency'],
                                     [i['doc_id'] for i in group] + [credits[i['invoice_id']]['row_id'] for i in group]))
    paid_by_invoice, bank_outflow = defaultdict(int), 0
    for payment in payments.values():
        target = invoices[payment['remittance_invoice_id']]
        amount, stamp = payment['amount_minor'], payment['timestamp']
        _require(_positive(amount) and payment['currency'] == target['currency'], 'invalid payment amount or currency')
        _require(start <= _moment(stamp) <= end and _moment(stamp) >= _moment(target['issued_at']) and
                 _moment(stamp).date() == _moment(target['issued_at']).date(), 'only same-day settlements supported')
        paid_by_invoice[target['invoice_id']] += amount
        _require(paid_by_invoice[target['invoice_id']] <= target['total_minor'], 'remittances exceed invoice total')
        refs, allocated, seen = payment['invoice_refs'], 0, set()
        _require(isinstance(refs, list), 'allocation references must be a list')
        evidence = [target['doc_id'], payment['doc_id']]
        for ref in refs:
            other = invoices[ref['invoice_id']]
            _require(other['entity_id'] == target['entity_id'] and other['currency'] == payment['currency'], 'allocation scope mismatch')
            _require(_positive(ref['amount_minor']) and ref['invoice_id'] not in seen, 'invalid allocation')
            seen.add(ref['invoice_id'])
            allocated += ref['amount_minor']
            evidence.append(other['doc_id'])
        _require(allocated <= amount, 'allocations exceed available payment')
        rows = payment_rows[payment['payment_id']]
        _require(len(rows) == 2, 'payment journal incomplete')
        debit = next(r for r in rows if r['account'] == 'payable')
        credit = next(r for r in rows if r['account'] == 'bank')
        _require(debit['debit_minor'] == credit['credit_minor'] and debit['credit_minor'] == credit['debit_minor'] == 0, 'unbalanced payment')
        _require(all(r['invoice_id'] == target['invoice_id'] and r['entity_id'] == target['entity_id'] and
                     _moment(r['timestamp']) == _moment(stamp) and r['line_id'] is None and
                     r['reporting_period'] == _moment(stamp).strftime('%Y-%m') for r in rows), 'payment posting scope mismatch')
        rate, rate_id = correct_rate(payment['currency'], stamp)
        used_id = debit['rate_id']
        _require(credit['rate_id'] == used_id, 'inconsistent applied rate')
        if payment['currency'] == 'KZT':
            _require(used_id is None, 'domestic payment cannot use FX')
            used_rate = '1'
        else:
            used_rate = by_rate[used_id]['rate']
        _require(debit['debit_minor'] == _rounded(amount, used_rate), 'posting differs from declared rate')
        expected = _rounded(amount, rate)
        gap = abs(expected - debit['debit_minor'])
        evidence.extend(r['row_id'] for r in rows)
        if rate_id is not None:
            evidence.append(rate_id)
        if gap or used_id != rate_id:
            findings.append(_finding('fx_rate_or_date', [payment['payment_id'], debit['row_id']], gap, 'KZT',
                                     [target['doc_id'], payment['doc_id'], debit['row_id'], credit['row_id'], rate_id]))
        target_allocation = sum(r['amount_minor'] for r in refs if r['invoice_id'] == target['invoice_id'])
        if target_allocation != amount:
            findings.append(_finding('payment_allocation', [target['invoice_id'], payment['payment_id']],
                                     _rounded(amount - target_allocation, rate), 'KZT', evidence))
        bank_outflow += credit['credit_minor']
    _require(len(opening) == 2, 'opening capital journal required')
    bank = next(r for r in opening if r['account'] == 'bank')
    equity = next(r for r in opening if r['account'] == 'equity')
    _require(bank['debit_minor'] == equity['credit_minor'] and bank['credit_minor'] == equity['debit_minor'] == 0
             and bank['debit_minor'] >= bank_outflow, 'opening funding insufficient or unbalanced')
    _require(all(r['entity_id'] == manifest['company_id'] and r['line_id'] is None and r['rate_id'] is None and
                 _moment(r['timestamp']) == start and r['reporting_period'] == start.strftime('%Y-%m') for r in opening), 'invalid opening scope')
    return sorted(findings, key=lambda f: (f['type'], f['affected_ids']))


def validate_company(public, truth):
    """Compare independently derived public findings with private issue labels."""
    findings = inspect_company(public)
    def signature(item, amount_key):
        return item['type'], tuple(sorted(item['affected_ids'])), item[amount_key], item['currency']
    try:
        expected = {signature(f, 'claimed_amount_minor'): set(f['evidence_ids']) for f in findings}
        issues = truth['issues']
        _require(isinstance(issues, list) and len(issues) == len(expected) <= 12, 'truth count mismatch')
        remaining, private_ids = set(expected), set()
        public_ids = {v for rows in public['tables'].values() for row in rows for k, v in row.items()
                      if k.endswith('_id') and isinstance(v, str)}
        for issue in issues:
            key = signature(issue, 'expected_amount_minor')
            _require(type(issue['expected_amount_minor']) is int and key in remaining, 'truth differs from public facts')
            _require(len(issue['affected_ids']) == len(set(issue['affected_ids'])), 'duplicate affected ID')
            remaining.remove(key)
            _require(isinstance(issue['issue_id'], str) and issue['issue_id'] and issue['issue_id'] not in private_ids | public_ids, 'invalid private issue ID')
            private_ids.add(issue['issue_id'])
            sets = issue['allowed_evidence_sets']
            _require(isinstance(sets, list) and sets, 'missing evidence')
            for evidence in sets:
                _require(isinstance(evidence, list) and 0 < len(evidence) <= 10 and len(set(evidence)) == len(evidence)
                         and expected[key] <= set(evidence) <= public_ids, 'unsupported evidence')
    except (KeyError, TypeError) as exc:
        raise ValueError('malformed company truth') from exc
