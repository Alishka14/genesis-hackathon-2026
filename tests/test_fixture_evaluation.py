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
