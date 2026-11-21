"""Trusted, conservative same-currency allocation; no guesses or truth labels.

This checks explicit documentary references, not findings against hidden truth.
See docs/MATCHING_SPEC.md for scope, atomicity and ambiguity semantics.
"""
from collections import defaultdict
from datetime import datetime, timezone
from itertools import groupby
import re


def _identifier(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('invalid identifier')
    return value


def _currency(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Z]{3}', value):
        raise ValueError('invalid currency')
    return value


def _amount(value, *, zero=False):
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError('amount must be integer minor units in supported range')
    return value


def _instant(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be an offset datetime')
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('timestamp requires timezone')
    return stamp.astimezone(timezone.utc)


def _records(records, *, payment=False):
    if not isinstance(records, list):
        raise ValueError('records must be a list')
    key = 'payment_id' if payment else 'invoice_id'
    result = {}
    try:
        for source in records:
            if not isinstance(source, dict):
                raise ValueError('record must be an object')
            id = _identifier(source[key])
            if id in result:
                raise ValueError('duplicate document identifier')
            item = {'id': id, 'entity': _identifier(source['entity_id']),
                    'currency': _currency(source['currency']),
                    'instant': _instant(source['timestamp' if payment else 'issued_at']),
                    'amount': _amount(source['amount_minor' if payment else 'total_minor'], zero=payment)}
            if payment:
                if source.get('kind', 'payment') != 'payment':
                    raise ValueError('refunds and reversals require a separate movement model')
                refs = source['invoice_refs']
                if not isinstance(refs, list):
                    raise ValueError('invoice_refs must be a list')
                item['refs'] = []
                for ref in refs:
                    if not isinstance(ref, dict) or set(ref) != {'invoice_id', 'amount_minor'}:
                        raise ValueError('invalid allocation reference')
                    item['refs'].append((_identifier(ref['invoice_id']), _amount(ref['amount_minor'])))
            else:
                item['status'] = source.get('status', 'issued')
                if item['status'] not in ('issued', 'cancelled'):
                    raise ValueError('unsupported invoice status')
            result[id] = item
    except KeyError as exc:
        raise ValueError('missing required allocation field') from exc
    return result


def allocate_payments(invoices, payments):
    """Return allocations, unapplied money and per-invoice balances.

    Both inputs are internal records with entity_id. Only positive ordinary
    same-currency references can be applied. Zero payments with no references
    remain unapplied. Invalid schema/unsupported refund movements raise ValueError.
    Business-invalid references return INVALID; unsupported FX returns UNSUPPORTED.
    No input is mutated. Rows and IDs cannot decide simultaneous conflicts.
    """
    bills = _records(invoices)
    transfers = _records(payments, payment=True)
    balances = {id: {'currency': b['currency'], 'paid_minor': 0, 'outstanding_minor': b['amount']}
                for id, b in sorted(bills.items())}
    results = {}
    ordered = sorted(transfers.values(), key=lambda p: (p['instant'], p['id']))
    for _, group in groupby(ordered, key=lambda p: p['instant']):
        batch = list(group)
        proposed = {}
        demand = defaultdict(int)
        for p in batch:
            result = {'status': 'UNALLOCATED', 'currency': p['currency'], 'allocations': [],
                      'unallocated_minor': p['amount'], 'candidate_ids': [], 'errors': []}
            results[p['id']] = result
            if not p['refs']:
                result['candidate_ids'] = sorted(id for id, b in bills.items()
                    if b['entity'] == p['entity'] and b['currency'] == p['currency']
                    and b['status'] == 'issued' and b['instant'] <= p['instant']
                    and balances[id]['outstanding_minor'] > 0)
                if p['amount'] > 0 and len(result['candidate_ids']) > 1:
                    result['status'] = 'AMBIGUOUS'
                continue
            errors, seen = set(), set()
            if sum(amount for _, amount in p['refs']) > p['amount']:
                errors.add('PAYMENT_CAPACITY')
            for id, amount in p['refs']:
                if id in seen:
                    errors.add('DUPLICATE_REFERENCE')
                seen.add(id)
                b = bills.get(id)
                if b is None:
                    errors.add('UNKNOWN_INVOICE')
                    continue
                if b['entity'] != p['entity']:
                    errors.add('WRONG_ENTITY')
                if b['status'] != 'issued':
                    errors.add('INVOICE_NOT_PAYABLE')
                if b['instant'] > p['instant']:
                    errors.add('INVOICE_NOT_YET_ISSUED')
                if b['currency'] != p['currency']:
                    errors.add('FX_POLICY_REQUIRED')
                elif amount > balances[id]['outstanding_minor']:
                    errors.add('INVOICE_CAPACITY')
            if errors:
                result['status'] = 'UNSUPPORTED' if errors == {'FX_POLICY_REQUIRED'} else 'INVALID'
                result['errors'] = sorted(errors)
                continue
            proposed[p['id']] = p['refs']
            for id, amount in p['refs']:
                demand[id] += amount
        conflicts = {id for id, amount in demand.items() if amount > balances[id]['outstanding_minor']}
        for pid, refs in proposed.items():
            result = results[pid]
            if any(id in conflicts for id, _ in refs):
                result['status'] = 'AMBIGUOUS'
                result['errors'] = ['SIMULTANEOUS_CAPACITY_CONFLICT']
                result['candidate_ids'] = sorted(id for id, _ in refs)
                continue
            for id, amount in sorted(refs):
                result['allocations'].append({'invoice_id': id, 'amount_minor': amount, 'basis': 'explicit_invoice_ref'})
                balances[id]['paid_minor'] += amount
                balances[id]['outstanding_minor'] -= amount
                result['unallocated_minor'] -= amount
            result['status'] = 'PARTIAL' if result['unallocated_minor'] else 'ALLOCATED'
    return {'payments': dict(sorted(results.items())), 'invoice_balances': balances}


def validate_clean_company_allocations(public):
    """Additional pre-injection check for the existing company model.

    Its payments omit entity_id. Derive that internal field from the clean
    payment journal, never from the potentially incorrect invoice_refs.
    This is not a replacement for company_checks or a new public schema.
    """
    tables = public['tables']
    entities = defaultdict(set)
    for row in tables['ledger']:
        if row.get('payment_id') is not None:
            entities[row['payment_id']].add(_identifier(row['entity_id']))
    transfers = []
    for payment in tables['payments']:
        owners = entities[payment['payment_id']]
        if len(owners) != 1:
            raise ValueError('clean payment requires consistent journal entity')
        transfers.append({**payment, 'entity_id': next(iter(owners))})
    result = allocate_payments(tables['invoices'], transfers)
    if any(p['status'] != 'ALLOCATED' or p['unallocated_minor'] != 0 for p in result['payments'].values()):
        raise ValueError('clean company payment is not fully and validly allocated')
    return result
