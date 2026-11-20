import json
import subprocess
import sys
import pytest
from ledgergym.episode_io import load_public_episode
from ledgergym.fixture_evaluation import evaluate_fixture_dataset


def test_company_dataset_has_twenty_reproducible_disjoint_episodes(tmp_path):
    from ledgergym.company_dataset import create_company_dataset
    first, second = tmp_path / 'a', tmp_path / 'b'
    index = create_company_dataset(first, seed=42)
    create_company_dataset(second, seed=42)
    assert len(index['train']) == len(index['dev']) == 10
    ids, private_seeds = set(), set()
    for split in ('train', 'dev'):
        types, compounds, sizes, counts = set(), set(), set(), []
        for entry in index[split]:
            folder = first / entry['path']
            public = load_public_episode(folder / 'public')
            truth = json.loads((folder / 'private/truth.json').read_text())
            provenance = json.loads((folder / 'private/provenance.json').read_text())
            assert entry['episode_id'] not in ids and provenance['seed'] not in private_seeds
            ids.add(entry['episode_id'])
            private_seeds.add(provenance['seed'])
            postings = len(public['tables']['ledger'])
            documents = len(public['tables']['invoices']) + len(public['tables']['payments'])
            assert 200 <= postings <= 2000 and 20 <= documents <= 200
            sizes.add(postings)
            counts.append(len(truth['issues']))
            types.update(i['type'] for i in truth['issues'])
            compounds.update(c['kind'] for c in provenance['compound_groups'])
        assert types == {'duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period'}
        assert compounds == {'fx_allocation', 'duplicate_allocation'}
        assert min(counts) == 0 and max(counts) == 12 and len(sizes) > 1
    assert {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()} == {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()}
    text = json.dumps(index)
    assert all(secret not in text for secret in ('seed', 'faults', 'compounds', 'private'))


def test_company_dataset_evaluation_replays_all_non_oracle_policies(tmp_path):
    from ledgergym.company_dataset import create_company_dataset
    root = tmp_path / 'dataset'
    create_company_dataset(root, seed=19)
    output = tmp_path / 'evaluation'
    summary = evaluate_fixture_dataset(root, output)
    assert summary['kind'] == 'synthetic_company_development'
    assert summary['replay'] == {'trajectories': 60, 'score_matches': 60}
    for split in ('train', 'dev'):
        assert all(v['episodes'] == 10 for v in summary['splits'][split].values())
        assert summary['splits'][split]['reconciliation']['mean_f1'] == 1
    assert summary['policies']['reconciliation']['mean_reward'] < 1
    assert summary['policies']['oracle']['mean_reward'] == 1
    actions = [json.loads(line) for line in (output / 'trajectories.jsonl').read_text().splitlines()]
    assert len(actions) == 60 and all(r['policy'] != 'oracle' for r in actions)
    assert all('from_step' in json.dumps(r['actions']) for r in actions)
    serialized = json.dumps(actions)
    assert all(secret not in serialized for secret in ('issue_id', 'expected_amount_minor', 'private-', 'interventions', '"seed":'))


def test_company_dataset_never_overwrites_existing_directory(tmp_path):
    from ledgergym.company_dataset import create_company_dataset
    marker = tmp_path / 'marker'
    marker.write_text('keep')
    with pytest.raises(FileExistsError):
        create_company_dataset(tmp_path)
    assert marker.read_text() == 'keep'


def test_offline_company_cli_builds_dataset_and_evaluates(tmp_path):
    root = tmp_path / 'company'
    result = subprocess.run([sys.executable, '-m', 'ledgergym.company_dataset', str(root), '--evaluate'], capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report['train'] == report['dev'] == 10
    assert report['replay']['score_matches'] == 60
    assert (root / 'evaluation/summary.json').is_file()
