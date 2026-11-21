"""Hand-calculated fixtures independent of the company generator."""
import copy
import pytest


def manual_company():
    stamp = '2026-01-31T23:30:00+00:00'  # February 1 in the policy timezone.
    def row(key, account, debit, credit, inv=None, pay=None, line=None, rate='rate-current'):
        return {'row_id': key, 'timestamp': stamp, 'account': account, 'debit_minor': debit,
                'credit_minor': credit, 'currency': 'KZT', 'entity_id': 'supplier',
                'invoice_id': inv, 'payment_id': pay, 'line_id': line,
                'rate_id': rate, 'reporting_period': '2026-02'}
    opening = [row('fund-bank', 'bank', 1000, 0, rate=None), row('fund-equity', 'equity', 0, 1000, rate=None)]
    for r in opening:
        r.update(entity_id='company', timestamp='2026-02-01T00:00:00+05:00')
    tables = {
        'invoices': [{'doc_id': 'invoice-doc', 'invoice_id': 'invoice', 'entity_id': 'supplier',
                      'issued_at': stamp, 'due_at': '2026-02-15T00:00:00+05:00', 'currency': 'USD', 'total_minor': 101,
                      'line_items': [{'line_id': 'line-1', 'service_ref': 'service', 'description': 'A', 'amount_minor': 1},
                                     {'line_id': 'line-2', 'service_ref': 'service', 'description': 'B', 'amount_minor': 100}]}],
        'payments': [{'doc_id': 'payment-doc', 'payment_id': 'payment', 'timestamp': stamp, 'currency': 'USD',
                      'amount_minor': 51, 'remittance_invoice_id': 'invoice',
                      'invoice_refs': [{'invoice_id': 'invoice', 'amount_minor': 51}]}],
        'ledger': opening + [row('expense-1', 'expense', 2, 0, 'invoice', line='line-1'),
                             row('expense-2', 'expense', 150, 0, 'invoice', line='line-2'),
                             row('invoice-credit', 'payable', 0, 152, 'invoice'),
                             row('payment-debit', 'payable', 76, 0, 'invoice', 'payment'),
                             row('payment-credit', 'bank', 0, 76, 'invoice', 'payment')],
        'fx': [{'rate_id': 'rate-previous', 'date': '2026-01-31', 'source_currency': 'USD', 'target_currency': 'KZT', 'rate': '1.25'},
               {'rate_id': 'rate-current', 'date': '2026-02-01', 'source_currency': 'USD', 'target_currency': 'KZT', 'rate': '1.50'}],
    }
    return {'manifest': {'schema_version': '0.3-company', 'episode_id': 'manual-company', 'company_id': 'company',
                         'base_currency': 'KZT', 'period_start': '2026-02-01T00:00:00+05:00',
                         'period_end': '2026-02-28T23:59:59+05:00', 'timezone': '+05:00',
                         'rounding': 'ROUND_HALF_EVEN', 'counts': {k: len(v) for k, v in tables.items()}},
            'policy': {'accounting_model': 'accrual_company_v1', 'rounding': 'ROUND_HALF_EVEN',
                       'currency_exponents': {'KZT': 2, 'USD': 2}, 'fx_date': 'local_transaction_date',
                       'cutoff_timezone': '+05:00', 'period_rule': 'calendar_month_of_transaction',
                       'invoice_rounding': 'round_total_residual_to_last_line',
                       'duplicate_rule': 'one_invoice_per_service_ref',
                       'allocation_rule': 'allocate_full_payment_to_remittance_invoice',
                       'allocation_claim_currency': 'KZT'}, 'tables': tables}


def test_manual_rounding_and_timezone_boundary_are_clean():
    from ledgergym.company_checks import inspect_company
    # 101*1.50=151.5 ->152; 51*1.50=76.5 ->76 (ties to even).
    assert inspect_company(manual_company()) == []


def test_manual_fx_allocation_amounts_use_correct_rate_not_posted_money():
    from ledgergym.company_checks import inspect_company
    public = manual_company()
    public['tables']['payments'][0]['invoice_refs'][0]['amount_minor'] = 25
    for r in public['tables']['ledger']:
        if r['payment_id']:
            r['rate_id'] = 'rate-previous'
            if r['debit_minor']:
                r['debit_minor'] = 64
            else:
                r['credit_minor'] = 64
    findings = inspect_company(public)
    assert {(f['type'], f['claimed_amount_minor'], f['currency']) for f in findings} == {
        ('fx_rate_or_date', 12, 'KZT'), ('payment_allocation', 39, 'KZT')}
    assert all('rate-current' in f['evidence_ids'] for f in findings)


def test_manual_wrong_period_uses_local_month_and_converted_invoice_amount():
    from ledgergym.company_checks import inspect_company
    public = manual_company()
    for r in public['tables']['ledger']:
        if r['invoice_id'] and r['payment_id'] is None:
            r['reporting_period'] = '2026-01'
    findings = inspect_company(public)
    assert len(findings) == 1
    assert findings[0]['type'] == 'reporting_period'
    assert findings[0]['claimed_amount_minor'] == 152
    assert findings[0]['affected_ids'] == ['invoice']
    assert set(findings[0]['evidence_ids']) == {'invoice-doc', 'invoice-credit'}


@pytest.mark.parametrize('change', ['orphan', 'overallocated', 'currency', 'bool_money', 'balance', 'rate_provenance', 'naive_date', 'invoice_total', 'duplicate_id'])
def test_manual_integrity_errors_are_rejected(change):
    from ledgergym.company_checks import inspect_company
    p = manual_company()
    if change == 'orphan':
        p['tables']['payments'][0]['remittance_invoice_id'] = 'missing'
    elif change == 'overallocated':
        p['tables']['payments'][0]['invoice_refs'][0]['amount_minor'] = 52
    elif change == 'currency':
        p['tables']['ledger'][-1]['currency'] = 'USD'
    elif change == 'bool_money':
        p['tables']['payments'][0]['amount_minor'] = True
    elif change == 'balance':
        p['tables']['ledger'][-1]['credit_minor'] += 1
    elif change == 'rate_provenance':
        p['tables']['ledger'][-1]['rate_id'] = 'missing'
    elif change == 'naive_date':
        p['tables']['payments'][0]['timestamp'] = '2026-02-01T00:00:00'
    elif change == 'invoice_total':
        p['tables']['invoices'][0]['total_minor'] += 1
    else:
        p['tables']['ledger'][-1]['row_id'] = p['tables']['ledger'][0]['row_id']
    with pytest.raises(ValueError):
        inspect_company(p)


def test_wrong_fx_date_remains_a_policy_fault_even_if_value_is_equal():
    from ledgergym.company_checks import inspect_company
    public = manual_company()
    public['tables']['fx'][0]['rate'] = '1.50'
    for row in public['tables']['ledger']:
        if row['payment_id']:
            row['rate_id'] = 'rate-previous'
    findings = inspect_company(public)
    assert len(findings) == 1 and findings[0]['type'] == 'fx_rate_or_date'
    assert findings[0]['claimed_amount_minor'] == 0


def test_allocation_container_must_be_a_list():
    from ledgergym.company_checks import inspect_company
    public = manual_company()
    public['tables']['payments'][0]['invoice_refs'] = {}
    with pytest.raises(ValueError):
        inspect_company(public)


def test_manual_equal_amounts_are_not_duplicates_without_business_identity():
    from ledgergym.company_checks import inspect_company
    public = manual_company()
    second = copy.deepcopy(public['tables']['invoices'][0])
    second.update(invoice_id='invoice-2', doc_id='invoice-doc-2')
    for line in second['line_items']:
        line['line_id'] += '-second'
        line['service_ref'] = 'different-service'
    public['tables']['invoices'].append(second)
    extra = []
    for row in public['tables']['ledger']:
        if row['invoice_id'] == 'invoice' and row['payment_id'] is None:
            row = copy.deepcopy(row)
            row['row_id'] += '-second'
            row['invoice_id'] = 'invoice-2'
            if row['line_id'] is not None:
                row['line_id'] += '-second'
            extra.append(row)
    public['tables']['ledger'].extend(extra)
    public['manifest']['counts'] = {k: len(v) for k, v in public['tables'].items()}
    assert inspect_company(public) == []
    for line in second['line_items']:
        line['service_ref'] = 'service'
    findings = inspect_company(public)
    assert len(findings) == 1
    assert findings[0]['type'] == 'duplicate_invoice'
    assert findings[0]['claimed_amount_minor'] == 101 and findings[0]['currency'] == 'USD'
    assert set(findings[0]['affected_ids']) == {'invoice', 'invoice-2'}
    assert set(findings[0]['evidence_ids']) == {'invoice-doc', 'invoice-doc-2', 'invoice-credit', 'invoice-credit-second'}
