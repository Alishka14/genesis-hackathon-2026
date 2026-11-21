import pytest
from ledgergym.baselines import run_baseline
from ledgergym.generator import generate_episode


@pytest.mark.parametrize('scenario', ['duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period', 'fx_allocation', 'duplicate_allocation'])
def test_reconciliation_baseline_investigates_development_fixtures(scenario):
    public, truth = generate_episode(19, {'scenario': scenario})
    report = run_baseline(public, truth, 'reconciliation')
    assert report['score']['tp'] == len(truth['issues'])
    assert report['score']['fp'] == 0 and report['score']['fn'] == 0
    assert report['trajectory'][-1]['action'] == 'submit'
    assert 'issue_id' not in repr(report['trajectory'])
    assert 'expected_amount_minor' not in repr(report['trajectory'])


def test_reconciliation_remains_silent_on_clean_fixture():
    public, truth = generate_episode(19, {'scenario': 'duplicate_invoice', 'fault': False})
    report = run_baseline(public, truth, 'reconciliation')
    assert report['score']['f1'] == 1 and report['score']['fp'] == 0


def test_mark_all_attacks_clean_fixture_and_seeded_random_replays():
    public, truth = generate_episode(19, {'scenario': 'duplicate_invoice', 'fault': False})
    assert run_baseline(public, truth, 'mark_all')['score']['fp'] > 0
    assert run_baseline(public, truth, 'seeded_random', seed=7) == run_baseline(public, truth, 'seeded_random', seed=7)


def test_oracle_is_evaluator_only_and_not_exported_as_trajectory():
    public, truth = generate_episode(19, {'scenario': 'fx_allocation'})
    report = run_baseline(public, truth, 'oracle')
    assert report['score']['tp'] == 2 and report['score']['fp'] == 0
    assert report['trajectory'] is None
