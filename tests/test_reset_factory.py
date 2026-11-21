import copy
import json
import pytest
from ledgergym.env import LedgerSandbox
from ledgergym.generator import generate_episode


def submit_empty(env, initial):
    return env.step({'action': 'submit', 'episode_id': initial['manifest']['episode_id'], 'findings': []})


def test_reset_changes_episode_documents_and_bound_evaluator():
    env = LedgerSandbox()
    first, _ = env.reset(seed=11, config={'scenario': 'duplicate_invoice', 'fault': True})
    old_doc = env.step({'action': 'list_records', 'table': 'invoices'})[0]['records'][0]['doc_id']
    assert submit_empty(env, first)[4]['score']['fn'] == 1
    second, info = env.reset(seed=12, config={'scenario': 'payment_allocation', 'fault': False})
    assert second['manifest']['episode_id'] != first['manifest']['episode_id']
    assert second['remaining_steps'] == 100 and info == {}
    assert env.step({'action': 'get_document', 'doc_id': old_doc})[0]['error'] == 'invalid_action'
    result = submit_empty(env, second)
    assert result[1] == 0.998 and result[4]['score']['fn'] == 0


@pytest.mark.parametrize('scenario', ['duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period', 'fx_allocation', 'duplicate_allocation'])
def test_generated_reset_repeats_public_data_and_scores(scenario):
    env = LedgerSandbox()
    runs = []
    for _ in range(2):
        initial, info = env.reset(seed=42, config={'scenario': scenario})
        rows = env.step({'action': 'list_records', 'table': 'ledger'})[0]
        runs.append((initial, info, rows, submit_empty(env, initial)))
    assert runs[0] == runs[1]
    assert runs[0][-1][4]['score']['fn'] == (2 if scenario.endswith('allocation') and scenario != 'payment_allocation' else 1)


def test_closed_reset_does_not_export_private_fields_or_terminal_score():
    env = LedgerSandbox(closed=True)
    initial, info = env.reset(seed=9988776655, config={'scenario': 'duplicate_invoice'})
    result = submit_empty(env, initial)
    serialized = json.dumps([initial, info, result])
    for private in ('9988776655', 'issue_id', 'expected_amount_minor', 'provenance', 'allowed_evidence_sets'):
        assert private not in serialized
    assert result[1:] == (0.0, True, False, {})


def test_reset_without_seed_creates_new_episode():
    env = LedgerSandbox()
    first, _ = env.reset()
    second, _ = env.reset()
    assert first['manifest']['episode_id'] != second['manifest']['episode_id']


@pytest.mark.parametrize('seed,config', [(True, None), ('42', None), (1, {}), (1, {'scenario': 'unknown'}), (1, {'scenario': 'duplicate_invoice', 'fault': 1})])
def test_failed_reset_disables_previous_episode_until_valid_reset(seed, config):
    env = LedgerSandbox()
    env.reset(seed=10)
    with pytest.raises(ValueError):
        env.reset(seed=seed, config=config)
    with pytest.raises(RuntimeError):
        env.step({'action': 'calculator', 'expression': '1+1'})
    initial, _ = env.reset(seed=20, config={'scenario': 'reporting_period', 'fault': False})
    assert submit_empty(env, initial)[1] == 1.0


def test_fixed_episode_rejects_generation_arguments():
    public, _ = generate_episode(1, {'scenario': 'duplicate_invoice'})
    env = LedgerSandbox(public, lambda findings, steps: {'reward': 0})
    with pytest.raises(ValueError):
        env.reset(seed=2)
    with pytest.raises(ValueError):
        env.reset(config={'scenario': 'reporting_period'})
    assert env.reset()[0]['manifest'] == public['manifest']


def test_factory_reset_replaces_cursors_and_copies_public_input():
    public, _ = generate_episode(1, {'scenario': 'duplicate_invoice'})
    def factory(seed, config):
        return public, lambda findings, steps: {'reward': 0}
    env = LedgerSandbox(episode_factory=factory)
    env.reset(seed=1)
    first_page = env.step({'action': 'list_records', 'table': 'ledger', 'limit': 1})[0]
    snapshot = copy.deepcopy(first_page['records'])
    public['tables']['ledger'][0]['debit_minor'] = 999999
    assert env.step({'action': 'list_records', 'table': 'ledger', 'limit': 1})[0]['records'] == snapshot
    env.reset(seed=1)
    assert env.step({'action': 'list_records', 'table': 'ledger', 'cursor': first_page['next_cursor']})[0]['error'] == 'invalid_action'
    assert env.step({'action': 'list_records', 'table': 'ledger', 'limit': 1})[0]['records'][0]['debit_minor'] == 999999
