"""Two small linked financial examples; public schemas are provisional."""
import copy
import random
from .fx_world import make_fx_episode, validate_fx_episode, _convert
from .world import make_episode, validate_episode


_RULE = 'allocate_full_payment_to_remittance_invoice'


def _private_id(seed, domain):
    rng = random.Random(f'{seed}:{domain}:ledgergym-private')
    return f'private-{rng.getrandbits(128):032x}'


def make_fx_allocation(seed, fx_fault=True, allocation_fault=True):
    public, truth = make_fx_episode(seed, 'wrong_date' if fx_fault else 'none')
    invoice, payment = public['tables']['invoices'][0], public['tables']['payments'][0]
    public['policy']['allocation_rule'] = _RULE
    public['policy']['allocation_claim_currency'] = 'KZT'
    payment['remittance_invoice_id'] = invoice['invoice_id']
    amount = payment['amount_minor']
    allocated = amount // 2 if allocation_fault else amount
    payment['invoice_refs'] = [{'invoice_id': invoice['invoice_id'], 'amount_minor': allocated}]
    if allocation_fault:
        rows = public['tables']['ledger']
        correct_rate = next(r for r in public['tables']['fx'] if r['date'] == payment['timestamp'][:10])
        truth['issues'].append({'issue_id': _private_id(seed, 'fx-allocation'), 'type': 'payment_allocation', 'affected_ids': [invoice['invoice_id'], payment['payment_id']], 'expected_amount_minor': _convert(amount - allocated, correct_rate['rate']), 'currency': 'KZT', 'allowed_evidence_sets': [[invoice['doc_id'], payment['doc_id'], *[r['row_id'] for r in rows], correct_rate['rate_id']]]})
    validate_compound(public, truth)
    return public, truth


def make_duplicate_allocation(seed, duplicate_fault=True, allocation_fault=True):
    public, truth = make_episode(seed, duplicate_fault)
    first, second = public['tables']['invoices']
    rng = random.Random(f'{seed}:duplicate-allocation:public')
    payment_id, doc_id, row1, row2 = [f'id-{rng.getrandbits(128):032x}' for _ in range(4)]
    amount = first['total_minor'] // 2
    public['policy']['allocation_rule'] = _RULE
    payment = {'doc_id': doc_id, 'payment_id': payment_id, 'timestamp': first['issued_at'], 'currency': first['currency'], 'amount_minor': amount, 'remittance_invoice_id': first['invoice_id'], 'invoice_refs': [{'invoice_id': second['invoice_id'] if allocation_fault else first['invoice_id'], 'amount_minor': amount}]}
    public['tables']['payments'] = [payment]
    for row_id, account, debit, credit in [(row1, 'payable', amount, 0), (row2, 'bank', 0, amount)]:
        public['tables']['ledger'].append({'row_id': row_id, 'timestamp': payment['timestamp'], 'account': account, 'debit_minor': debit, 'credit_minor': credit, 'currency': payment['currency'], 'entity_id': first['entity_id'], 'invoice_id': None, 'payment_id': payment_id})
    public['manifest']['counts']['payments'] = 1
    public['manifest']['counts']['ledger'] = len(public['tables']['ledger'])
    if allocation_fault:
        truth['issues'].append({'issue_id': _private_id(seed, 'duplicate-allocation'), 'type': 'payment_allocation', 'affected_ids': [first['invoice_id'], payment_id], 'expected_amount_minor': amount, 'currency': payment['currency'], 'allowed_evidence_sets': [[first['doc_id'], second['doc_id'], doc_id, row1, row2]]})
    validate_compound(public, truth)
    return public, truth


def validate_compound(public, truth):
    """Recompute each fault from public data; reject missing or extra issues."""
    def reject(reason):
        raise ValueError(reason)
    try:
        tables, policy = public['tables'], public['policy']
        if policy['allocation_rule'] != _RULE or len(tables['payments']) != 1:
            reject('invalid allocation policy or payment count')
        if any(public['manifest']['counts'][name] != len(tables[name]) for name in tables):
            reject('manifest count mismatch')
        invoice_by_id = {i['invoice_id']: i for i in tables['invoices']}
        payment = tables['payments'][0]
        target = invoice_by_id.get(payment['remittance_invoice_id'])
        refs = payment['invoice_refs']
        amount = payment['amount_minor']
        if target is None or type(amount) is not int or amount <= 0 or amount > target['total_minor'] or not isinstance(refs, list) or len(refs) != 1:
            reject('invalid remittance or amount')
        ref = refs[0]
        if not isinstance(ref, dict) or set(ref) != {'invoice_id', 'amount_minor'} or ref['invoice_id'] not in invoice_by_id or type(ref['amount_minor']) is not int or not 0 < ref['amount_minor'] <= amount:
            reject('invalid allocation')
        if payment['currency'] != target['currency'] or invoice_by_id[ref['invoice_id']]['currency'] != payment['currency']:
            reject('currency mismatch')
        public_ids = [v for rows in tables.values() for row in rows for key, v in row.items() if key in {'invoice_id', 'doc_id', 'payment_id', 'row_id', 'rate_id'} and isinstance(v, str)]
        ids_for_records = [i['invoice_id'] for i in tables['invoices']] + [i['doc_id'] for i in tables['invoices']] + [payment['payment_id'], payment['doc_id']] + [r['row_id'] for r in tables['ledger']] + [r['rate_id'] for r in tables['fx']]
        if any(not isinstance(x, str) or not x for x in ids_for_records) or len(set(ids_for_records)) != len(ids_for_records):
            reject('record IDs are not unique')
        issues = truth['issues']
        if not isinstance(issues, list) or any(i['type'] not in {'payment_allocation', 'fx_rate_or_date', 'duplicate_invoice'} for i in issues):
            reject('unsupported truth')
        allocated_to_target = ref['amount_minor'] if ref['invoice_id'] == target['invoice_id'] else 0
        gap = amount - allocated_to_target
        allocation_issues = [i for i in issues if i['type'] == 'payment_allocation']
        if len(allocation_issues) != int(gap > 0):
            reject('incorrect allocation truth count')
        if tables['fx']:
            if len(tables['invoices']) != 1 or len(tables['ledger']) != 2:
                reject('unsupported FX compound')
            rows = tables['ledger']
            base = copy.deepcopy(public)
            base['tables']['payments'][0]['invoice_refs'] = [{'invoice_id': target['invoice_id'], 'amount_minor': amount}]
            other_truth = {'issues': [i for i in issues if i['type'] != 'payment_allocation']}
            validate_fx_episode(base, other_truth)
            if policy.get('allocation_claim_currency') != 'KZT':
                reject('invalid allocation valuation currency')
            correct_rate = next(r for r in tables['fx'] if r['date'] == payment['timestamp'][:10])
            expected_amount = _convert(gap, correct_rate['rate'])
            expected_currency = 'KZT'
            required = {target['doc_id'], payment['doc_id'], correct_rate['rate_id'], *[r['row_id'] for r in rows]}
        else:
            if len(tables['invoices']) != 2 or len(tables['ledger']) != 6:
                reject('unsupported duplicate compound')
            payment_rows = [r for r in tables['ledger'] if r['payment_id'] == payment['payment_id']]
            if len(payment_rows) != 2 or {(r['account'], r['debit_minor'], r['credit_minor']) for r in payment_rows} != {('payable', amount, 0), ('bank', 0, amount)}:
                reject('invalid payment journal')
            if any(r['invoice_id'] is not None or r['entity_id'] != target['entity_id'] or r['currency'] != payment['currency'] or r['timestamp'] != payment['timestamp'] for r in payment_rows):
                reject('invalid payment row references')
            base = copy.deepcopy(public)
            base['tables']['payments'] = []
            base['tables']['ledger'] = [r for r in base['tables']['ledger'] if r['payment_id'] is None]
            base['manifest']['counts']['payments'] = 0
            base['manifest']['counts']['ledger'] = len(base['tables']['ledger'])
            other_truth = {'issues': [i for i in issues if i['type'] != 'payment_allocation']}
            validate_episode(base, other_truth)
            expected_amount, expected_currency = gap, payment['currency']
            required = {target['doc_id'], invoice_by_id[ref['invoice_id']]['doc_id'], payment['doc_id'], *[r['row_id'] for r in payment_rows]}
        if gap:
            issue = allocation_issues[0]
            if set(issue['affected_ids']) != {target['invoice_id'], payment['payment_id']} or issue['expected_amount_minor'] != expected_amount or issue['currency'] != expected_currency or not issue['allowed_evidence_sets']:
                reject('incorrect allocation truth')
            if any(not isinstance(s, list) or not required <= set(s) or not set(s) <= set(public_ids) for s in issue['allowed_evidence_sets']):
                reject('invalid allocation evidence')
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('malformed compound episode') from exc
