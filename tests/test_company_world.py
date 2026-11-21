import copy
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
import pytest
from ledgergym.generator import generate_episode
from ledgergym.env import LedgerSandbox
from ledgergym.baselines import run_baseline
from ledgergym.replay import replay_actions


@pytest.mark.parametrize('postings,documents', [(200, 20), (401, 80), (2000, 200), (2000, 20)])
def test_company_has_exact_size_balanced_journals_and_real_line_components(postings, documents):
    public, truth = generate_episode(81, {'scenario': 'company', 'postings': postings, 'documents': documents})
    t = public['tables']
    assert len(t['ledger']) == postings
    assert len(t['invoices']) + len(t['payments']) == documents
    assert truth['issues'] == []
    assert all(type(r['debit_minor']) is int and type(r['credit_minor']) is int for r in t['ledger'])
    assert sum(r['debit_minor'] - r['credit_minor'] for r in t['ledger']) == 0
    line_ids = {line['line_id'] for i in t['invoices'] for line in i['line_items']}
    expense = [r for r in t['ledger'] if r['account'] == 'expense']
    assert {r['line_id'] for r in expense} == line_ids
    assert len(expense) == len(line_ids)
    assert len({i['total_minor'] for i in t['invoices']}) > 3
    for invoice in t['invoices']:
        rows = [r for r in t['ledger'] if r['invoice_id'] == invoice['invoice_id'] and r['payment_id'] is None]
        assert sum(r['debit_minor'] for r in rows) == sum(r['credit_minor'] for r in rows) > 0
        assert sum(l['amount_minor'] for l in invoice['line_items']) == invoice['total_minor']


def test_company_repeatability_and_clean_hard_negatives():
    config = {'scenario': 'company', 'postings': 400, 'documents': 80}
    public, truth = generate_episode(10, config)
    assert (public, truth) == generate_episode(10, config)
    assert public != generate_episode(11, config)[0]
    invoices = public['tables']['invoices']
    equal_amounts = Counter((i['entity_id'], i['currency'], i['total_minor']) for i in invoices)
    assert max(equal_amounts.values()) >= 2
    assert len({i['line_items'][0]['service_ref'] for i in invoices}) == len(invoices)
    by_id = {i['invoice_id']: i for i in invoices}
    assert any(p['amount_minor'] < by_id[p['remittance_invoice_id']]['total_minor'] for p in public['tables']['payments'])
    assert any(datetime.fromisoformat(i['issued_at']).month != datetime.fromisoformat(i['issued_at']).astimezone(timezone(timedelta(hours=5))).month for i in invoices)
    assert run_baseline(public, truth, 'reconciliation')['score']['f1'] == 1


@pytest.mark.parametrize('fault', ['duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period'])
def test_each_company_fault_is_switchable_and_supported_by_public_evidence(fault):
    config = {'scenario': 'company', 'faults': {fault: 3}}
    public, truth = generate_episode(42, config)
    assert Counter(i['type'] for i in truth['issues']) == {fault: 3}
    report = run_baseline(public, truth, 'reconciliation')
    assert (report['score']['tp'], report['score']['fp'], report['score']['fn']) == (3, 0, 0)
    assert replay_actions(LedgerSandbox(), report['trajectory'], seed=42, config=config)['steps'][-1][4]['score'] == report['score']


@pytest.mark.parametrize('compound,types', [('fx_allocation', {'fx_rate_or_date', 'payment_allocation'}), ('duplicate_allocation', {'duplicate_invoice', 'payment_allocation'})])
def test_company_compounds_share_evidence_and_record_private_interventions(compound, types):
    from ledgergym.company_world import build_company
    public, truth, provenance = build_company(7, {'compounds': {compound: 1}})
    assert {i['type'] for i in truth['issues']} == types
    evidence = [set(i['allowed_evidence_sets'][0]) for i in truth['issues']]
    assert len(evidence[0] & evidence[1]) >= 2
    assert provenance['seed'] == 7 and provenance['interventions']
    assert all(change['before'] != change['after'] for change in provenance['interventions'])
    serialized = json.dumps(public)
    assert all(key not in serialized for key in ('issue_id', 'expected_amount_minor', 'provenance', 'fault_hint', 'interventions'))
    assert run_baseline(public, truth, 'reconciliation')['score']['tp'] == 2


def test_twelve_mixed_faults_are_found_within_environment_budget_at_max_size():
    config = {'scenario': 'company', 'postings': 2000, 'documents': 200,
              'faults': {'duplicate_invoice': 2, 'payment_allocation': 2, 'fx_rate_or_date': 2, 'reporting_period': 2},
              'compounds': {'fx_allocation': 1, 'duplicate_allocation': 1}}
    public, truth = generate_episode(11, config)
    assert len(truth['issues']) == 12
    assert all(0 < len(e) <= 10 for i in truth['issues'] for e in i['allowed_evidence_sets'])
    report = run_baseline(public, truth, 'reconciliation')
    assert (report['score']['tp'], report['score']['fp'], report['score']['fn']) == (12, 0, 0)
    assert len(report['trajectory']) <= 100
    assert run_baseline(public, truth, 'oracle')['score']['f1'] == 1


@pytest.mark.parametrize('extra', [
    {'postings': 199}, {'postings': 2001}, {'postings': True}, {'documents': 19}, {'documents': 201},
    {'postings': 200, 'documents': 200}, {'faults': {'duplicate_invoice': 13}},
    {'faults': {'unknown': 1}}, {'faults': {'reporting_period': True}}, {'faults': {'reporting_period': -1}},
    {'compounds': {'fx_allocation': 7}}, {'compounds': {'unknown': 1}},
    {'documents': 20, 'faults': {'fx_rate_or_date': 12}}, {'typo': 1},
])
def test_company_rejects_impossible_or_unknown_configuration(extra):
    with pytest.raises(ValueError):
        generate_episode(1, {'scenario': 'company', **extra})


def test_company_validator_rejects_balanced_but_invented_money_and_forged_truth():
    from ledgergym.company_checks import validate_company
    public, truth = generate_episode(33, {'scenario': 'company'})
    changed = copy.deepcopy(public)
    invoice = changed['tables']['invoices'][0]
    rows = [r for r in changed['tables']['ledger'] if r['invoice_id'] == invoice['invoice_id'] and r['payment_id'] is None]
    next(r for r in rows if r['account'] == 'expense')['debit_minor'] += 1
    next(r for r in rows if r['account'] == 'payable')['credit_minor'] += 1
    with pytest.raises(ValueError):
        validate_company(changed, truth)
    broken, faulty_truth = generate_episode(33, {'scenario': 'company', 'faults': {'duplicate_invoice': 1}})
    with pytest.raises(ValueError):
        validate_company(broken, {'issues': []})
    forged = copy.deepcopy(faulty_truth)
    forged['issues'][0]['expected_amount_minor'] += 1
    with pytest.raises(ValueError):
        validate_company(broken, forged)
    forged = copy.deepcopy(faulty_truth)
    forged['issues'][0]['allowed_evidence_sets'] = [['nonexistent']]
    with pytest.raises(ValueError):
        validate_company(broken, forged)


def test_company_validation_and_score_do_not_depend_on_row_order():
    from ledgergym.company_checks import validate_company
    public, truth = generate_episode(4, {'scenario': 'company', 'compounds': {'fx_allocation': 1, 'duplicate_allocation': 1}})
    expected = run_baseline(public, truth, 'reconciliation')['score']
    for rows in public['tables'].values():
        rows.reverse()
    validate_company(public, truth)
    assert run_baseline(public, truth, 'reconciliation')['score'] == expected


def test_company_roundtrip_preserves_public_nulls_and_private_provenance(tmp_path):
    from ledgergym.company_world import build_company
    from ledgergym.episode_io import export_episode, load_public_episode
    from ledgergym.company_checks import validate_company
    public, truth, provenance = build_company(9, {'compounds': {'fx_allocation': 1, 'duplicate_allocation': 1}})
    root = tmp_path / 'episode'
    export_episode(root, public, truth, seed=9, provenance=provenance)
    loaded = load_public_episode(root / 'public')
    assert loaded == public
    validate_company(loaded, truth)
    assert json.loads((root / 'private/provenance.json').read_text()) == provenance
    assert json.loads((root / 'private/truth.json').read_text()) == truth
    assert len(list((root / 'public').iterdir())) == 6
    assert 'interventions' not in ''.join(p.read_text() for p in (root / 'public').iterdir())
    assert run_baseline(loaded, truth, 'reconciliation')['score']['tp'] == 4


def test_company_export_requires_matching_private_provenance_before_creating_folder(tmp_path):
    from ledgergym.company_world import build_company
    from ledgergym.episode_io import export_episode
    public, truth, provenance = build_company(9, {})
    root = tmp_path / 'missing'
    with pytest.raises(ValueError):
        export_episode(root, public, truth, seed=9)
    assert not root.exists()
    provenance['seed'] = 8
    with pytest.raises(ValueError):
        export_episode(root, public, truth, seed=9, provenance=provenance)
    assert not root.exists()


def test_private_interventions_completely_restore_clean_history():
    from ledgergym.company_world import build_company
    from ledgergym.company_checks import validate_company
    config = {'faults': {kind: 1 for kind in ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')},
              'compounds': {'fx_allocation': 1, 'duplicate_allocation': 1}}
    public, _, provenance = build_company(17, config)
    for change in reversed(provenance['interventions']):
        table = change['table']
        if table == 'invoices.line_items':
            records = [line for inv in public['tables']['invoices'] for line in inv['line_items']]
            key = 'line_id'
        else:
            records = public['tables'][table]
            key = 'row_id' if table == 'ledger' else 'payment_id'
        record = next(r for r in records if r[key] == change['id'])
        assert record[change['field']] == change['after']
        record[change['field']] = change['before']
    validate_company(public, {'issues': []})
    assert public == build_company(17, {})[0]


def test_company_findings_survive_consistent_id_renaming():
    from ledgergym.company_checks import validate_company
    public, truth = generate_episode(23, {'scenario': 'company', 'compounds': {'fx_allocation': 1, 'duplicate_allocation': 1}})
    replacements = {}
    def rename(value):
        if isinstance(value, dict):
            return {k: rename(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        if isinstance(value, str) and value.startswith('id-'):
            return replacements.setdefault(value, f'renamed-{len(replacements)}')
        return value
    public, truth = rename(public), rename(truth)
    validate_company(public, truth)
    assert run_baseline(public, truth, 'reconciliation')['score']['tp'] == 4


def test_company_generation_is_independent_of_callers_decimal_context():
    from decimal import Inexact, localcontext
    config = {'scenario': 'company', 'compounds': {'fx_allocation': 1}}
    expected = generate_episode(3, config)
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        assert generate_episode(3, config) == expected
