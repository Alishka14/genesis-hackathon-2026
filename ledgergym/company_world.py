"""Coherent synthetic accrual histories with explicit private interventions."""
import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import random
from .company_checks import validate_company
from .payment_matching import validate_clean_company_allocations


VERSION = 'company-0.1'
FAULTS = ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')
COMPOUNDS = ('fx_allocation', 'duplicate_allocation')
_ZONE = timezone(timedelta(hours=5))


def _convert(amount, rate):
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        return int((Decimal(amount) * Decimal(rate)).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))


def _config(config):
    if not isinstance(config, dict) or set(config) - {'postings', 'documents', 'faults', 'compounds'}:
        raise ValueError('unknown company configuration')
    postings, documents = config.get('postings', 400), config.get('documents', 80)
    if type(postings) is not int or not 200 <= postings <= 2000 or type(documents) is not int or not 20 <= documents <= 200:
        raise ValueError('company size out of range')
    if postings < 2 * documents + 2:
        raise ValueError('not enough postings for documents and opening capital')
    result = {'postings': postings, 'documents': documents}
    for key, allowed in [('faults', FAULTS), ('compounds', COMPOUNDS)]:
        counts = config.get(key, {})
        if not isinstance(counts, dict) or set(counts) - set(allowed) or any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError('invalid fault counts')
        result[key] = {name: counts.get(name, 0) for name in allowed}
    if sum(result['faults'].values()) + 2 * sum(result['compounds'].values()) > 12:
        raise ValueError('at most twelve faults are supported')
    return result


def _plan(seed, config, payment_count):
    """Reserve disjoint business pairs; compound faults share a single pair."""
    rng = random.Random(f'company-fault-plan:{seed}')
    available = set(range(payment_count))
    plan = []
    order = [('fx_allocation', config['compounds']['fx_allocation']),
             ('duplicate_allocation', config['compounds']['duplicate_allocation']),
             ('fx_rate_or_date', config['faults']['fx_rate_or_date']),
             ('duplicate_invoice', config['faults']['duplicate_invoice']),
             ('payment_allocation', config['faults']['payment_allocation']),
             ('reporting_period', config['faults']['reporting_period'])]
    for kind, count in order:
        for _ in range(count):
            candidates = sorted(available)
            if kind in ('fx_allocation', 'fx_rate_or_date'):
                candidates = [i for i in candidates if i % 2 == 1]
                if kind == 'fx_allocation':
                    candidates = [i for i in candidates if i < 12]
            elif kind in ('duplicate_invoice', 'duplicate_allocation'):
                candidates = [i for i in candidates if i % 2 == 0]
            if not candidates:
                raise ValueError('not enough eligible business operations for fault mix')
            index = rng.choice(candidates)
            available.remove(index)
            plan.append((kind, index))
    return plan


def build_company(seed, config):
    """Return (public, truth, private provenance) after clean and faulty checks.

    The seed, normalized config, before/after values and issue IDs are private.
    Changing only fault switches leaves the clean company and its IDs unchanged.
    """
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    config = _config(config)
    payment_count = config['documents'] // 3
    invoice_count = config['documents'] - payment_count
    plan = _plan(seed, config, payment_count)
    rng = random.Random(f'{VERSION}:{seed}')
    def new_id():
        return f'id-{rng.getrandbits(128):032x}'
    company_id, episode_id = new_id(), f'episode-{rng.getrandbits(128):032x}'
    entities = [new_id() for _ in range(max(4, invoice_count // 8))]
    line_counts = [1] * invoice_count
    for _ in range(config['postings'] - 2 * config['documents'] - 2):
        line_counts[rng.randrange(invoice_count)] += 1
    fx = []
    initial_rate = rng.randint(43000, 47000)
    for day in range(29):
        hundredths = initial_rate + 13 * day
        fx.append({'rate_id': new_id(), 'date': (date(2026, 1, 31) + timedelta(days=day)).isoformat(),
                   'source_currency': 'USD', 'target_currency': 'KZT',
                   'rate': f'{hundredths // 100}.{hundredths % 100:02d}'})
    by_date = {r['date']: r for r in fx}
    def quote(currency, stamp):
        if currency == 'KZT':
            return '1', None
        rate = by_date[datetime.fromisoformat(stamp).astimezone(_ZONE).date().isoformat()]
        return rate['rate'], rate['rate_id']
    invoices, payments, ledger, pairs = [], [], [], []
    credits, payment_journals = {}, {}
    def posting(account, debit, credit, entity, stamp, invoice=None, payment=None, line=None, rate=None):
        row = {'row_id': new_id(), 'timestamp': stamp, 'account': account, 'debit_minor': debit,
               'credit_minor': credit, 'currency': 'KZT', 'entity_id': entity, 'invoice_id': invoice,
               'payment_id': payment, 'line_id': line, 'rate_id': rate,
               'reporting_period': datetime.fromisoformat(stamp).astimezone(_ZONE).strftime('%Y-%m')}
        ledger.append(row)
        return row
    for pair_index in range((invoice_count + 1) // 2):
        entity = rng.choice(entities)
        currency = 'USD' if pair_index % 2 else 'KZT'
        total = rng.randint(100000, 500000)
        if pair_index == 0 or (pair_index % 2 == 1 and pair_index < 12):
            stamp = '2026-01-31T23:30:00+00:00'
        else:
            stamp = f'2026-02-{rng.randint(2, 24):02d}T{rng.randint(8, 17):02d}:30:00+05:00'
        category = rng.choice(['hosting', 'equipment support', 'licensing', 'training', 'maintenance'])
        pair = []
        for _ in range(min(2, invoice_count - len(invoices))):
            invoice_id, doc_id, service = new_id(), new_id(), new_id()
            count = line_counts[len(invoices)]
            weights = [rng.randint(1, 9) for _ in range(count)]
            amounts = [1 + (total - count) * w // sum(weights) for w in weights]
            amounts[-1] += total - sum(amounts)
            lines = [{'line_id': new_id(), 'service_ref': service, 'description': f'Synthetic {category} component {i + 1}',
                      'amount_minor': amount} for i, amount in enumerate(amounts)]
            invoice = {'doc_id': doc_id, 'invoice_id': invoice_id, 'entity_id': entity, 'issued_at': stamp,
                       'due_at': (datetime.fromisoformat(stamp).astimezone(_ZONE) + timedelta(days=14)).isoformat(),
                       'currency': currency, 'total_minor': total, 'line_items': lines}
            invoices.append(invoice)
            pair.append(invoice)
            rate, rate_id = quote(currency, stamp)
            converted = _convert(total, rate)
            parts = [_convert(amount, rate) for amount in amounts[:-1]]
            parts.append(converted - sum(parts))
            for line, amount in zip(lines, parts):
                posting('expense', amount, 0, entity, stamp, invoice_id, line=line['line_id'], rate=rate_id)
            credits[invoice_id] = posting('payable', 0, converted, entity, stamp, invoice_id, rate=rate_id)
        pairs.append(pair)
    outflow = 0
    for pair_index in range(payment_count):
        target = pairs[pair_index][0]
        total = target['total_minor']
        amount = total if pair_index % 4 == 0 else total * rng.choice([1, 2, 3]) // 4
        payment_id = new_id()
        payment = {'doc_id': new_id(), 'payment_id': payment_id, 'timestamp': target['issued_at'],
                   'currency': target['currency'], 'amount_minor': amount, 'remittance_invoice_id': target['invoice_id'],
                   'invoice_refs': [{'invoice_id': target['invoice_id'], 'amount_minor': amount}]}
        payments.append(payment)
        rate, rate_id = quote(payment['currency'], payment['timestamp'])
        converted = _convert(amount, rate)
        outflow += converted
        payment_journals[payment_id] = [
            posting('payable', converted, 0, target['entity_id'], payment['timestamp'], target['invoice_id'], payment_id, rate=rate_id),
            posting('bank', 0, converted, target['entity_id'], payment['timestamp'], target['invoice_id'], payment_id, rate=rate_id)]
    start = '2026-02-01T00:00:00+05:00'
    funding = outflow * 2 + 100000
    posting('bank', funding, 0, company_id, start)
    posting('equity', 0, funding, company_id, start)
    tables = {'invoices': invoices, 'payments': payments, 'ledger': ledger, 'fx': fx}
    public = {'manifest': {'schema_version': '0.3-company', 'episode_id': episode_id, 'company_id': company_id,
                           'base_currency': 'KZT', 'period_start': start, 'period_end': '2026-02-28T23:59:59+05:00',
                           'timezone': '+05:00', 'rounding': 'ROUND_HALF_EVEN', 'counts': {k: len(v) for k, v in tables.items()}},
              'policy': {'accounting_model': 'accrual_company_v1', 'rounding': 'ROUND_HALF_EVEN',
                         'currency_exponents': {'KZT': 2, 'USD': 2}, 'fx_date': 'local_transaction_date',
                         'cutoff_timezone': '+05:00', 'period_rule': 'calendar_month_of_transaction',
                         'invoice_rounding': 'round_total_residual_to_last_line',
                         'duplicate_rule': 'one_invoice_per_service_ref',
                         'allocation_rule': 'allocate_full_payment_to_remittance_invoice', 'allocation_claim_currency': 'KZT'},
              'tables': tables}
    validate_company(public, {'issues': []})
    validate_clean_company_allocations(public)
    truth = {'issues': []}
    provenance = {'seed': seed, 'generator_version': VERSION, 'config': copy.deepcopy(config),
                  'clean_preflight': 'passed', 'interventions': [], 'compound_groups': []}
    private_rng = random.Random(f'{VERSION}:private:{seed}')
    def change(table, record, field, value, key):
        provenance['interventions'].append({'table': table, 'id': record[key], 'field': field,
                                           'before': copy.deepcopy(record[field]), 'after': copy.deepcopy(value)})
        record[field] = value
    def issue(kind, affected, amount, currency, evidence):
        item = {'issue_id': f'private-{private_rng.getrandbits(128):032x}', 'type': kind,
                'affected_ids': sorted(affected), 'expected_amount_minor': amount, 'currency': currency,
                'allowed_evidence_sets': [sorted(set(evidence))]}
        truth['issues'].append(item)
        return item['issue_id']
    for kind, pair_index in plan:
        first, second = pairs[pair_index]
        payment = payments[pair_index]
        rows = payment_journals[payment['payment_id']]
        rate, rate_id = quote(payment['currency'], payment['timestamp'])
        group = []
        if kind in ('duplicate_invoice', 'duplicate_allocation'):
            service = first['line_items'][0]['service_ref']
            for line in second['line_items']:
                change('invoices.line_items', line, 'service_ref', service, 'line_id')
            group.append(issue('duplicate_invoice', [first['invoice_id'], second['invoice_id']], second['total_minor'], second['currency'],
                               [first['doc_id'], second['doc_id'], credits[first['invoice_id']]['row_id'], credits[second['invoice_id']]['row_id']]))
        if kind in ('fx_rate_or_date', 'fx_allocation'):
            previous = (datetime.fromisoformat(payment['timestamp']).astimezone(_ZONE).date() - timedelta(days=1)).isoformat()
            wrong_rate = by_date[previous]
            wrong = _convert(payment['amount_minor'], wrong_rate['rate'])
            for row in rows:
                change('ledger', row, 'rate_id', wrong_rate['rate_id'], 'row_id')
                change('ledger', row, 'debit_minor' if row['account'] == 'payable' else 'credit_minor', wrong, 'row_id')
            group.append(issue('fx_rate_or_date', [payment['payment_id'], rows[0]['row_id']],
                               abs(_convert(payment['amount_minor'], rate) - wrong), 'KZT',
                               [first['doc_id'], payment['doc_id'], *[r['row_id'] for r in rows], rate_id]))
        if kind in ('payment_allocation', 'fx_allocation', 'duplicate_allocation'):
            amount = payment['amount_minor']
            wrong_target = kind == 'duplicate_allocation'
            refs = [{'invoice_id': second['invoice_id'] if wrong_target else first['invoice_id'],
                     'amount_minor': amount if wrong_target else amount // 2}]
            change('payments', payment, 'invoice_refs', refs, 'payment_id')
            gap = amount if wrong_target else amount - refs[0]['amount_minor']
            evidence = [first['doc_id'], payment['doc_id'], *[r['row_id'] for r in rows]]
            if wrong_target:
                evidence.append(second['doc_id'])
            if rate_id is not None:
                evidence.append(rate_id)
            group.append(issue('payment_allocation', [first['invoice_id'], payment['payment_id']], _convert(gap, rate), 'KZT', evidence))
        if kind == 'reporting_period':
            for row in ledger:
                if row['invoice_id'] == first['invoice_id'] and row['payment_id'] is None:
                    change('ledger', row, 'reporting_period', '2026-01', 'row_id')
            group.append(issue('reporting_period', [first['invoice_id']], _convert(first['total_minor'], rate), 'KZT',
                               [first['doc_id'], credits[first['invoice_id']]['row_id']]))
        if kind in COMPOUNDS:
            provenance['compound_groups'].append({'kind': kind, 'issue_ids': group, 'payment_id': payment['payment_id']})
    order_rng = random.Random(f'{VERSION}:order:{seed}')
    for table in tables.values():
        order_rng.shuffle(table)
    validate_company(public, truth)
    return public, truth, provenance
