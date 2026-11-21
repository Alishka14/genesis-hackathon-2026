"""Opt-in 10+10 clean-hard-negative development benchmark acceptance tests.

These are open internal cases and policies, not hidden GENESIS judge results.
"""
import copy
import json
import subprocess
import sys
from collections import Counter

import pytest

from ledgergym.baselines import run_baseline
from ledgergym.company_dataset import create_company_dataset
from ledgergym.episode_io import load_public_episode
from ledgergym.fixture_evaluation import evaluate_fixture_dataset


def _read_episodes(root, index):
    for split in ('train', 'dev'):
        for entry in index[split]:
            folder = root / entry['path']
            yield split, entry, folder, load_public_episode(folder / 'public'), json.loads(
                (folder / 'private' / 'truth.json').read_text())


def test_optional_settlement_mix_has_ten_disjoint_episodes_per_split(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    index = create_company_dataset(first, seed=88, include_settlement_hard_negatives=True)
    again = create_company_dataset(second, seed=88, include_settlement_hard_negatives=True)
    assert index == again
    assert index['kind'] == 'synthetic_company_development_with_settlements'
    assert len(index['train']) == len(index['dev']) == 10
    ids, private_seeds = set(), set()
    for split in ('train', 'dev'):
        models, fault_types, compounds = Counter(), set(), set()
        clean_count = 0
        for observed_split, entry, folder, public, truth in _read_episodes(first, {split: index[split], **{
            other: [] for other in ('train', 'dev') if other != split
        }}):
            assert observed_split == split
            episode_id = public['manifest']['episode_id']
            private = json.loads((folder / 'private' / 'provenance.json').read_text())
            assert episode_id == entry['episode_id'] and episode_id not in ids
            assert private['seed'] not in private_seeds
            ids.add(episode_id)
            private_seeds.add(private['seed'])
            model = public['policy']['accounting_model']
            models[model] += 1
            fault_types.update(issue['type'] for issue in truth['issues'])
            compounds.update(group['kind'] for group in private['compound_groups'])
            clean_count += not truth['issues']
            assert 200 <= len(public['tables']['ledger']) <= 2000
            assert 20 <= (len(public['tables']['payments']) +
                          len(public['tables']['invoices'])) <= 200
            if model == 'accrual_company_v2':
                assert truth == {'issues': []}
                payments = public['tables']['payments']
                assert len([p for p in payments if p['kind'] == 'refund']) == 1
                assert any(len(p['invoice_refs']) == 2 for p in payments if p['kind'] == 'payment')
                assert public['manifest']['schema_version'] == '0.4-company-settlements'
            else:
                assert model == 'accrual_company_v1'
        assert models == {'accrual_company_v1': 8, 'accrual_company_v2': 2}
        assert clean_count == 3
        assert fault_types == {'duplicate_invoice', 'payment_allocation',
                               'fx_rate_or_date', 'reporting_period'}
        assert compounds == {'fx_allocation', 'duplicate_allocation'}
    assert {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()} == {
        p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()
    }
    assert all(secret not in json.dumps(index) for secret in (
        '"seed"', '"faults"', '"compounds"', '"private"'))


def test_all_four_policies_measure_false_accusations_on_both_clean_models(tmp_path):
    root = tmp_path / 'data'
    create_company_dataset(root, seed=2026, include_settlement_hard_negatives=True)
    report = evaluate_fixture_dataset(root, tmp_path / 'report')
    assert report['kind'] == 'synthetic_company_development_with_settlements'
    assert report['replay'] == {'trajectories': 60, 'score_matches': 60}
    assert set(report['policies']) == {'seeded_random', 'reconciliation', 'mark_all', 'oracle'}
    assert report['model_counts'] == {
        'train': {'accrual_company_v1': 8, 'accrual_company_v2': 2},
        'dev': {'accrual_company_v1': 8, 'accrual_company_v2': 2},
    }
    assert report['policies']['reconciliation']['mean_f1'] == 1
    assert report['policies']['oracle']['mean_f1'] == 1
    assert report['policies']['oracle']['mean_reward'] == 1
    for split in ('train', 'dev'):
        assert all(policy['episodes'] == 10 for policy in report['splits'][split].values())

    clean = report['clean_false_accusations']
    for split, expected_legacy, expected_v2 in [('train', 1, 2), ('dev', 1, 2),
                                                 ('overall', 2, 4)]:
        for model, count in [('accrual_company_v1', expected_legacy),
                             ('accrual_company_v2', expected_v2)]:
            policies = clean[split][model]
            assert set(policies) == {'seeded_random', 'reconciliation', 'mark_all', 'oracle'}
            for name, row in policies.items():
                assert row['episodes'] == count
                assert 0 <= row['false_accusation_rate'] <= 1
                assert row['false_accusation_rate'] == row['false_accusation_episodes'] / count
                if name in ('oracle', 'reconciliation'):
                    assert row['fp'] == row['false_accusation_episodes'] == 0
                    assert row['false_accusation_rate'] == 0
                    assert row['mean_f1'] == 1
                else:
                    assert row['false_accusation_rate'] == 1
                    assert row['mean_f1'] == 0
                    assert row['fp'] >= count
            assert policies['oracle']['mean_reward'] == 1
            assert 0 < policies['reconciliation']['mean_reward'] < 1
            assert policies['mark_all']['fp'] == count * 30
            assert policies['seeded_random']['fp'] == count

    trajectories = [json.loads(line) for line in
                    (tmp_path / 'report/trajectories.jsonl').read_text().splitlines()]
    assert len(trajectories) == 60
    assert all(t['policy'] != 'oracle' and len(t['actions']) <= 100 for t in trajectories)
    text = json.dumps(trajectories, ensure_ascii=False)
    assert all(secret not in text for secret in (
        'issue_id', 'expected_amount_minor', 'allowed_evidence_sets', '"seed"', 'private-'))
    assert json.loads((tmp_path / 'report/summary.json').read_text()) == report


def test_reconciliation_baseline_rejects_corrupt_clean_v2_instead_of_hiding_fault(tmp_path):
    root = tmp_path / 'data'
    index = create_company_dataset(root, seed=101, include_settlement_hard_negatives=True)
    clean = next((public, truth) for _, _, _, public, truth in _read_episodes(root, index)
                 if public['policy']['accounting_model'] == 'accrual_company_v2')
    public, truth = clean
    broken = copy.deepcopy(public)
    split = next(p for p in broken['tables']['payments']
                 if p['kind'] == 'payment' and len(p['invoice_refs']) == 2)
    split['invoice_refs'][0]['amount_minor'] -= 1
    with pytest.raises(ValueError, match='payment allocation'):
        run_baseline(broken, truth, 'reconciliation')


def test_unsupported_dataset_option_is_rejected_before_any_write(tmp_path):
    root = tmp_path / 'not-created'
    with pytest.raises(ValueError):
        create_company_dataset(root, include_settlement_hard_negatives="yes")
    assert not root.exists()


def test_new_cli_mode_creates_extended_dataset_and_four_policy_report(tmp_path):
    root = tmp_path / 'extended'
    completed = subprocess.run([
        sys.executable, '-m', 'ledgergym.company_dataset', str(root),
        '--seed', '73', '--settlement-hard-negatives', '--evaluate'
    ], capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    assert result['train'] == result['dev'] == 10
    assert result['replay']['score_matches'] == 60
    summary = json.loads((root / 'evaluation/summary.json').read_text())
    assert summary['model_counts']['train']['accrual_company_v2'] == 2
    assert summary['clean_false_accusations']['dev']['accrual_company_v2']['reconciliation']['fp'] == 0
