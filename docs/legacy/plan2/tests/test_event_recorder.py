import copy
import json

import pytest

from ledgergym.env import LedgerSandbox
from ledgergym.generator import generate_episode
from ledgergym.replay import replay_actions
from ledgergym.event_recorder import public_events


def fixture(closed=False):
    public, _ = generate_episode(7, {'scenario': 'duplicate_invoice', 'fault': False})
    public['tables']['ledger'] = [{'row_id': f'row-{i}'} for i in range(103)]
    public['private'] = {'seed': 'PRIVATE-SEED', 'provenance': 'PRIVATE-PROVENANCE'}
    env = LedgerSandbox(public, lambda *args: {'reward': .75, 'secret': 'PRIVATE-SCORE'}, closed=closed)
    actions = [{'action': 'list_records', 'table': 'ledger'},
               {'action': 'list_records', 'table': 'ledger', 'cursor': {'from_step': 0}},
               {'action': 'list_records', 'table': 'ledger', 'cursor': {'from_step': 1}},
               {'action': 'submit', 'episode_id': public['manifest']['episode_id'], 'findings': []}]
    return env, actions


def test_complete_public_events_are_repeatable_detached_and_portable():
    env, actions = fixture()
    replay = replay_actions(env, actions)
    replay['info']['private'] = 'PRIVATE-RESET'
    snapshot = copy.deepcopy(replay)
    events = public_events(actions, replay)
    assert events == public_events(actions, replay_actions(env, actions))
    assert len(events) == 5
    assert events[0]['step'] == -1 and events[0]['action'] is None
    assert events[0]['observation'] == replay['initial']
    assert [e['step'] for e in events[1:]] == [0, 1, 2, 3]
    assert events[-1]['reward'] == .75 and events[-1]['terminated']
    assert not any(e['truncated'] for e in events)
    assert [e['observation'].get('next_cursor') for e in events[1:4]] == [{'from_step': 0}, {'from_step': 1}, None]
    assert all(set(e) == {'event_format', 'episode_id', 'step', 'action', 'observation', 'reward', 'terminated', 'truncated'} for e in events)
    serialized = json.dumps(events)
    assert 'PRIVATE-' not in serialized
    assert replay['steps'][0][0]['next_cursor'] not in serialized
    assert replay == snapshot
    assert replay_actions(env, [e['action'] for e in events[1:]])['steps'][-1][1] == .75
    events[0]['observation']['policy'].clear()
    events[1]['action']['table'] = 'bad'
    events[1]['observation']['records'].clear()
    assert replay == snapshot and actions[0]['table'] == 'ledger'


def test_closed_events_do_not_restore_evaluator_feedback():
    env, actions = fixture(closed=True)
    events = public_events(actions, replay_actions(env, actions))
    assert all(e['reward'] == 0 for e in events)
    assert 'PRIVATE-' not in json.dumps(events)


@pytest.mark.parametrize('actions, status, truncated', [
    ([{'action': 'unknown'}], 'invalid_action', False),
    ([{'action': 'submit'}], 'invalid_submit', False),
    ([{'action': 'calculator', 'expression': '1'}] * 100, 'finished', True),
])
def test_recorder_preserves_errors_partial_trajectories_and_truncation(actions, status, truncated):
    env, _ = fixture()
    events = public_events(actions, replay_actions(env, actions))
    assert len(events) == len(actions) + 1
    assert events[-1]['observation'].get('status', events[-1]['observation'].get('error')) == status
    assert events[-1]['truncated'] is truncated


def test_mismatched_action_and_response_counts_are_rejected():
    env, actions = fixture()
    with pytest.raises(ValueError):
        public_events(actions[:-1], replay_actions(env, actions))
