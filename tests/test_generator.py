import pytest
from ledgergym.generator import generate_episode


@pytest.mark.parametrize('scenario,expected', [('duplicate_invoice','duplicate_invoice'), ('payment_allocation','payment_allocation'), ('fx_rate_or_date','fx_rate_or_date'), ('reporting_period','reporting_period')])
def test_uniform_generator_provides_one_fault_or_clean_control(scenario, expected):
    public, truth = generate_episode(42, {'scenario': scenario, 'fault': True})
    assert [issue['type'] for issue in truth['issues']] == [expected]
    assert (public, truth) == generate_episode(42, {'scenario': scenario, 'fault': True})
    assert generate_episode(42, {'scenario': scenario, 'fault': False})[1]['issues'] == []


def test_uniform_generator_rejects_unknown_config():
    for config in ({'scenario': 'unknown'}, {'scenario':'duplicate_invoice','fault':1}, {'scenario':'duplicate_invoice','typo':True}, {'scenario':'fx_allocation','fault':True}):
        with pytest.raises(ValueError):
            generate_episode(1, config)


def test_invalid_scenario_type_is_a_clean_validation_error():
    with pytest.raises(ValueError):
        generate_episode(5, {'scenario': []})
