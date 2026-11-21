"""Hand-calculated payment allocation cases, independent of the generator."""
import copy
import random
import pytest


def invoice(id='i1', total=100, **fields):
    return {'invoice_id': id, 'entity_id': 'supplier', 'currency': 'KZT',
            'issued_at': '2026-02-01T10:00:00+05:00', 'total_minor': total, **fields}


def payment(id='p1', amount=100, refs=None, **fields):
    return {'payment_id': id, 'entity_id': 'supplier', 'currency': 'KZT',
            'timestamp': '2026-02-02T10:00:00+05:00', 'amount_minor': amount,
            'invoice_refs': [{'invoice_id': 'i1', 'amount_minor': amount}] if refs is None else refs,
            **fields}


def allocate(invoices, payments):
    from ledgergym.payment_matching import allocate_payments
    return allocate_payments(invoices, payments)


@pytest.mark.parametrize('amount,outstanding', [(100, 0), (40, 60), (1, 99)])
def test_full_and_partial_payments_preserve_invoice_balance(amount, outstanding):
    r = allocate([invoice()], [payment(amount=amount)])
    p = r['payments']['p1']
    assert p['status'] == 'ALLOCATED' and p['unallocated_minor'] == 0
    assert p['allocations'] == [{'invoice_id': 'i1', 'amount_minor': amount, 'basis': 'explicit_invoice_ref'}]
    assert r['invoice_balances']['i1'] == {'currency': 'KZT', 'paid_minor': amount, 'outstanding_minor': outstanding}


def test_multiple_payments_can_pay_one_invoice_without_double_counting():
    r = allocate([invoice()], [payment('p1', 40), payment('p2', 60)])
    assert r['invoice_balances']['i1']['paid_minor'] == 100
    assert all(p['status'] == 'ALLOCATED' for p in r['payments'].values())


def test_one_payment_splits_across_invoices_and_retains_overpayment():
    refs = [{'invoice_id': 'i1', 'amount_minor': 40}, {'invoice_id': 'i2', 'amount_minor': 60}]
    r = allocate([invoice(total=40), invoice('i2', 60)], [payment(amount=125, refs=refs)])
    p = r['payments']['p1']
    assert p['status'] == 'PARTIAL' and p['unallocated_minor'] == 25
    assert sum(a['amount_minor'] for a in p['allocations']) == 100
    assert [b['outstanding_minor'] for b in r['invoice_balances'].values()] == [0, 0]


@pytest.mark.parametrize('invoices,status,candidates', [
    ([], 'UNALLOCATED', []),
    ([invoice()], 'UNALLOCATED', ['i1']),
    ([invoice(), invoice('i2')], 'AMBIGUOUS', ['i1', 'i2']),
])
def test_absent_references_never_guess_even_with_one_equal_amount(invoices, status, candidates):
    p = allocate(invoices, [payment(refs=[])])['payments']['p1']
    assert p['status'] == status and p['candidate_ids'] == candidates
    assert p['allocations'] == [] and p['unallocated_minor'] == 100


@pytest.mark.parametrize('change,error', [
    ({'entity_id': 'other'}, 'WRONG_ENTITY'),
    ({'timestamp': '2026-01-01T00:00:00+00:00'}, 'INVOICE_NOT_YET_ISSUED'),
    ({'invoice_refs': [{'invoice_id': 'missing', 'amount_minor': 100}]}, 'UNKNOWN_INVOICE'),
    ({'invoice_refs': [{'invoice_id': 'i1', 'amount_minor': 60}, {'invoice_id': 'i1', 'amount_minor': 40}]}, 'DUPLICATE_REFERENCE'),
    ({'amount_minor': 50}, 'PAYMENT_CAPACITY'),
])
def test_invalid_reference_is_not_repaired_or_applied(change, error):
    pay = payment()
    pay.update(change)
    r = allocate([invoice()], [pay])
    p = r['payments']['p1']
    assert p['status'] == 'INVALID' and error in p['errors']
    assert p['allocations'] == [] and p['unallocated_minor'] == pay['amount_minor']
    assert r['invoice_balances']['i1']['paid_minor'] == 0


def test_cancelled_invoice_cannot_be_paid():
    p = allocate([invoice(status='cancelled')], [payment()])['payments']['p1']
    assert p['status'] == 'INVALID' and 'INVOICE_NOT_PAYABLE' in p['errors']


def test_invalid_part_of_split_does_not_apply_valid_part():
    refs = [{'invoice_id': 'i1', 'amount_minor': 40}, {'invoice_id': 'absent', 'amount_minor': 60}]
    r = allocate([invoice()], [payment(refs=refs), payment('p2')])
    assert r['payments']['p1']['allocations'] == []
    assert r['payments']['p2']['status'] == 'ALLOCATED'
    assert r['invoice_balances']['i1']['paid_minor'] == 100


def test_currency_conversion_without_explicit_policy_is_unsupported():
    p = allocate([invoice(currency='USD')], [payment()])['payments']['p1']
    assert p['status'] == 'UNSUPPORTED' and 'FX_POLICY_REQUIRED' in p['errors']
    assert p['allocations'] == [] and p['unallocated_minor'] == 100


def test_native_usd_amounts_do_not_get_summed_with_kzt():
    r = allocate([invoice(), invoice('usd', currency='USD')], [
        payment(), payment('usd-p', 40, [{'invoice_id': 'usd', 'amount_minor': 40}], currency='USD')])
    assert r['invoice_balances']['i1']['paid_minor'] == 100
    assert r['invoice_balances']['usd'] == {'currency': 'USD', 'paid_minor': 40, 'outstanding_minor': 60}


def test_equivalent_timestamps_conflicting_payments_do_not_choose_by_id():
    a = payment('z', 60)
    b = payment('a', 60, timestamp='2026-02-02T05:00:00+00:00')
    r = allocate([invoice()], [a, b])
    assert r['invoice_balances']['i1']['paid_minor'] == 0
    for p in r['payments'].values():
        assert p['status'] == 'AMBIGUOUS' and 'SIMULTANEOUS_CAPACITY_CONFLICT' in p['errors']
        assert p['unallocated_minor'] == 60


def test_chronologically_later_overallocation_is_rejected_not_truncated():
    r = allocate([invoice()], [payment('late', 40, timestamp='2026-02-03T10:00:00+05:00'), payment('early', 80)])
    assert r['invoice_balances']['i1']['paid_minor'] == 80
    assert r['payments']['late']['status'] == 'INVALID'
    assert r['payments']['late']['unallocated_minor'] == 40


def test_competing_split_is_atomic_and_does_not_block_unrelated_invoice():
    refs = [{'invoice_id': 'i1', 'amount_minor': 60}, {'invoice_id': 'i2', 'amount_minor': 20}]
    r = allocate([invoice(), invoice('i2'), invoice('i3')], [
        payment('a', 80, refs), payment('b', 60), payment('c', 30, [{'invoice_id': 'i3', 'amount_minor': 30}])])
    assert r['payments']['a']['status'] == r['payments']['b']['status'] == 'AMBIGUOUS'
    assert r['invoice_balances']['i2']['paid_minor'] == 0
    assert r['invoice_balances']['i3']['paid_minor'] == 30


def test_pure_function_and_order_invariance():
    invs = [invoice(), invoice('i2')]
    pays = [payment('a', 40), payment('b', 50, [{'invoice_id': 'i2', 'amount_minor': 50}])]
    before = copy.deepcopy((invs, pays))
    assert allocate(invs, pays) == allocate(list(reversed(invs)), list(reversed(pays)))
    assert (invs, pays) == before


def test_bijective_id_renaming_preserves_conflict_and_money():
    old = allocate([invoice()], [payment('a', 60), payment('b', 60)])
    new = allocate([invoice('renamed')], [payment('z', 60, [{'invoice_id': 'renamed', 'amount_minor': 60}]),
                                            payment('x', 60, [{'invoice_id': 'renamed', 'amount_minor': 60}])])
    assert old['invoice_balances']['i1'] == new['invoice_balances']['renamed']
    for a, b in [('a', 'z'), ('b', 'x')]:
        assert old['payments'][a]['status'] == new['payments'][b]['status'] == 'AMBIGUOUS'
        assert old['payments'][a]['unallocated_minor'] == new['payments'][b]['unallocated_minor'] == 60


@pytest.mark.parametrize('field,value', [('amount_minor', True), ('amount_minor', 1.5), ('amount_minor', -10),
    ('timestamp', '2026-02-02T10:00:00'), ('invoice_refs', None), ('entity_id', ''), ('currency', 'usd'), ('kind', 'refund')])
def test_malformed_or_unsupported_movement_is_rejected(field, value):
    p = payment()
    p[field] = value
    with pytest.raises(ValueError):
        allocate([invoice()], [p])


@pytest.mark.parametrize('ref_amount', [True, 0, -1, 1.5])
def test_reference_amount_requires_positive_integer(ref_amount):
    with pytest.raises(ValueError):
        allocate([invoice()], [payment(refs=[{'invoice_id': 'i1', 'amount_minor': ref_amount}])])


def test_duplicate_document_ids_cannot_be_silently_overwritten():
    with pytest.raises(ValueError):
        allocate([invoice(), invoice(total=200)], [payment()])
    with pytest.raises(ValueError):
        allocate([invoice()], [payment(), payment()])


def test_zero_payment_with_no_refs_creates_no_money():
    p = allocate([invoice()], [payment(amount=0, refs=[])])['payments']['p1']
    assert p['allocations'] == [] and p['unallocated_minor'] == 0


def test_candidates_exclude_wrong_entity_currency_future_and_cancelled():
    invoices = [invoice(), invoice('entity', entity_id='other'), invoice('usd', currency='USD'),
                invoice('future', issued_at='2026-02-04T00:00:00+00:00'), invoice('void', status='cancelled')]
    p = allocate(invoices, [payment(refs=[])])['payments']['p1']
    assert p['candidate_ids'] == ['i1'] and p['status'] == 'UNALLOCATED'


def clean_public():
    pay = payment()
    del pay['entity_id']
    return {'tables': {'invoices': [invoice()], 'payments': [pay], 'ledger': [
        {'payment_id': 'p1', 'entity_id': 'supplier'}, {'payment_id': 'p1', 'entity_id': 'supplier'}]}}


def test_company_adapter_uses_posting_entity_without_changing_public_fields():
    from ledgergym.payment_matching import validate_clean_company_allocations
    public = clean_public()
    before = copy.deepcopy(public)
    r = validate_clean_company_allocations(public)
    assert r['payments']['p1']['status'] == 'ALLOCATED'
    assert public == before


@pytest.mark.parametrize('case', ['foreign_entity', 'contradictory_entity', 'missing_postings', 'partial_reference'])
def test_company_adapter_rejects_inconsistent_clean_allocation(case):
    from ledgergym.payment_matching import validate_clean_company_allocations
    public = clean_public()
    if case == 'foreign_entity':
        for row in public['tables']['ledger']:
            row['entity_id'] = 'foreign'
    elif case == 'contradictory_entity':
        public['tables']['ledger'][0]['entity_id'] = 'foreign'
    elif case == 'missing_postings':
        public['tables']['ledger'] = []
    else:
        public['tables']['payments'][0]['invoice_refs'][0]['amount_minor'] = 40
    with pytest.raises(ValueError):
        validate_clean_company_allocations(public)


def test_seeded_conservation_and_order_matrix():
    # Independent conservation identities across 500 invoices / 2000 payments.
    # No production generator or allocation helper computes expected balances.
    for seed in range(100):
        rng = random.Random(seed)
        invoices = [invoice(f'i{i}', rng.randint(30, 200)) for i in range(5)]
        payments = []
        for j in range(20):
            refs = [{'invoice_id': i['invoice_id'], 'amount_minor': rng.randint(1, 100)}
                    for i in rng.sample(invoices, rng.randint(0, 3))]
            payments.append(payment(f'p{j}', sum(r['amount_minor'] for r in refs) + rng.randint(0, 50), refs,
                                    timestamp=f'2026-02-0{rng.randint(2, 4)}T00:00:00+05:00'))
        report = allocate(invoices, payments)
        paid = {i['invoice_id']: 0 for i in invoices}
        for p in payments:
            result = report['payments'][p['payment_id']]
            assert p['amount_minor'] == sum(a['amount_minor'] for a in result['allocations']) + result['unallocated_minor'], seed
            assert result['unallocated_minor'] >= 0, seed
            for a in result['allocations']:
                paid[a['invoice_id']] += a['amount_minor']
        for i in invoices:
            balance = report['invoice_balances'][i['invoice_id']]
            assert balance['paid_minor'] == paid[i['invoice_id']], seed
            assert balance['paid_minor'] + balance['outstanding_minor'] == i['total_minor'], seed
            assert 0 <= balance['paid_minor'] <= i['total_minor'], seed
        rng.shuffle(invoices)
        rng.shuffle(payments)
        assert report == allocate(invoices, payments), seed
