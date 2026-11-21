import copy
import json
import pytest
from ledgergym.baselines import run_baseline
from ledgergym.env import LedgerSandbox
from ledgergym.generator import generate_episode
from ledgergym.score import evaluate


def paginated_fixture():
    # Pagination-only fixture: no claim that these extra rows model accounting.
    public, truth = generate_episode(7, {'scenario': 'duplicate_invoice', 'fault': False})
    public['tables']['ledger'] = [{'row_id': f'row-{i}'} for i in range(103)]
    public['manifest']['counts']['ledger'] = 103
    ids = {f'row-{i}' for i in range(103)}
    return public, truth, LedgerSandbox(public, lambda findings, steps: evaluate([], findings, ids, steps))


def test_baseline_records_portable_cursor_references_and_replays_same_score():
    from ledgergym.replay import replay_actions
    public, truth, env = paginated_fixture()
    report = run_baseline(public, truth, 'reconciliation')
    actions = json.loads(json.dumps(report['trajectory']))
    assert [a['cursor'] for a in actions if 'cursor' in a] == [{'from_step': 2}, {'from_step': 3}]
    assert report == run_baseline(public, truth, 'reconciliation')
    snapshot = copy.deepcopy(actions)
    first = replay_actions(env, actions)
    second = replay_actions(env, actions)
    assert actions == snapshot
    assert first["executed_actions"] != actions
    assert isinstance(first["executed_actions"][3]["cursor"], str)
    assert first["executed_actions"][3]["cursor"] == first["steps"][2][0]["next_cursor"]
    assert isinstance(second["executed_actions"][3]["cursor"], str)
    for result in (first, second):
        rows = [row['row_id'] for action, step in zip(actions, result['steps']) if action.get('table') == 'ledger' for row in step[0]['records']]
        assert rows == [f'row-{i}' for i in range(103)]
        assert result['steps'][-1][4]['score'] == report['score']
        assert result['steps'][-1][1] == 0.988
    assert first['steps'][2][0]['next_cursor'] != second['steps'][2][0]['next_cursor']


@pytest.mark.parametrize('cursor', ['expired-token', {'from_step': -1}, {'from_step': 1}, {'from_step': True}, {'from_step': 0, 'extra': 1}, {'from_step': '0'}])
def test_replay_rejects_unresolvable_cursor_reference(cursor):
    from ledgergym.replay import replay_actions
    _, _, env = paginated_fixture()
    actions = [{'action': 'list_records', 'table': 'ledger'}, {'action': 'list_records', 'table': 'ledger', 'cursor': cursor}]
    with pytest.raises(ValueError):
        replay_actions(env, actions)


@pytest.mark.parametrize('first_table', ['invoices', 'payments'])
def test_replay_cannot_use_cursor_from_another_table_or_exhausted_page(first_table):
    from ledgergym.replay import replay_actions
    _, _, env = paginated_fixture()
    with pytest.raises(ValueError):
        replay_actions(env, [{'action': 'list_records', 'table': first_table, 'limit': 1}, {'action': 'list_records', 'table': 'ledger', 'cursor': {'from_step': 0}}])


def test_replay_repeated_page_references_do_not_skip_rows():
    from ledgergym.replay import replay_actions
    _, _, env = paginated_fixture()
    result = replay_actions(env, [{'action': 'list_records', 'table': 'ledger', 'limit': 1}, *[{'action': 'list_records', 'table': 'ledger', 'limit': 1, 'cursor': {'from_step': 0}} for _ in range(2)]])
    assert [s[0]['records'][0]['row_id'] for s in result['steps']] == ['row-0', 'row-1', 'row-1']


def test_replay_uses_seed_config_and_does_not_rewrite_wrong_episode_submit():
    from ledgergym.replay import replay_actions
    config = {'scenario': 'duplicate_invoice', 'fault': False}
    public, truth = generate_episode(7, config)
    actions = run_baseline(public, truth, 'reconciliation')['trajectory']
    assert replay_actions(LedgerSandbox(), actions, seed=7, config=config)['steps'][-1][1] == 0.992
    wrong = replay_actions(LedgerSandbox(), actions, seed=8, config=config)
    assert wrong['steps'][-1][0]['status'] == 'invalid_submit'
    closed = replay_actions(LedgerSandbox(closed=True), actions, seed=7, config=config)
    assert closed['steps'][-1][1:] == (0.0, True, False, {})


def test_replay_rejects_actions_after_terminal_step():
    from ledgergym.replay import replay_actions
    public, _, env = paginated_fixture()
    with pytest.raises(ValueError):
        replay_actions(env, [{'action': 'submit', 'episode_id': public['manifest']['episode_id'], 'findings': []}, {'action': 'calculator', 'expression': '1'}])


def test_replay_does_not_mutate_reused_action_objects():
    from ledgergym.replay import replay_actions
    _, _, env = paginated_fixture()
    repeat = {'action': 'list_records', 'table': 'ledger', 'limit': 1, 'cursor': {'from_step': 0}}
    result = replay_actions(env, [{'action': 'list_records', 'table': 'ledger', 'limit': 1}, repeat, repeat])
    assert result['steps'][1][0]['records'] == result['steps'][2][0]['records'] == [{'row_id': 'row-1'}]
