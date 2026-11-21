import json
from ledgergym.fixture_dataset import create_fixture_dataset
from ledgergym.fixture_evaluation import evaluate_fixture_dataset


def test_dataset_evaluation_records_only_public_policy_trajectories(tmp_path):
    dataset = tmp_path / 'input'
    output = tmp_path / 'report'
    create_fixture_dataset(dataset)
    evaluate_fixture_dataset(dataset, output)
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['kind'] == 'development_fixtures_not_benchmark'
    assert set(summary['policies']) == {'reconciliation', 'seeded_random', 'mark_all', 'oracle'}
    assert all(x['episodes'] == 20 for x in summary['policies'].values())
    trajectories = [json.loads(line) for line in (output / 'trajectories.jsonl').read_text().splitlines()]
    assert len(trajectories) == 60
    assert all(record['policy'] != 'oracle' for record in trajectories)
    serialized = json.dumps(trajectories)
    assert 'issue_id' not in serialized and 'expected_amount_minor' not in serialized and 'private-' not in serialized


def test_events_cover_every_action_without_changing_old_artifacts(tmp_path):
    dataset = tmp_path / 'input'
    create_fixture_dataset(dataset)
    first, second = tmp_path / 'first', tmp_path / 'second'
    evaluate_fixture_dataset(dataset, first)
    evaluate_fixture_dataset(dataset, second)
    for name in ('summary.json', 'trajectories.jsonl', 'events.jsonl'):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    trajectories = [json.loads(line) for line in (first / 'trajectories.jsonl').read_text().splitlines()]
    events = [json.loads(line) for line in (first / 'events.jsonl').read_text().splitlines()]
    assert len(events) == sum(len(t['actions']) + 1 for t in trajectories)
    for trajectory in trajectories:
        rows = [e for e in events if (e['episode_id'], e['policy']) == (trajectory['episode_id'], trajectory['policy'])]
        assert [e['action'] for e in rows[1:]] == trajectory['actions']
        assert rows[-1]['terminated'] and not rows[-1]['truncated']
        assert rows[0]['step'] == -1 and rows[0]['action'] is None
        assert all(e['split'] == trajectory['split'] for e in rows)
    assert not any(e['policy'] == 'oracle' for e in events)
    serialized = json.dumps(events)
    assert 'issue_id' not in serialized and 'expected_amount_minor' not in serialized and 'private-' not in serialized
