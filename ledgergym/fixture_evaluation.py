"""Evaluate open development datasets locally. Not a secure or independent benchmark."""
import argparse
import json
from pathlib import Path
import re
from .baselines import run_baseline
from .episode_io import load_public_episode
from .env import LedgerSandbox
from .replay import replay_actions
from .score import evaluate, accessible_evidence_ids


def evaluate_fixture_dataset(dataset, output):
    """Trusted evaluator only: reads private truth. Never mount it into an agent."""
    dataset = Path(dataset).resolve(strict=True)
    index = json.loads((dataset / 'index.json').read_text(encoding='utf-8'))
    company_kinds = {'synthetic_company_development',
                     'synthetic_company_development_with_settlements'}
    if index.get('kind') not in {'development_fixtures_not_benchmark', *company_kinds}:
        raise ValueError('expected a supported development dataset')
    extended = index['kind'] == 'synthetic_company_development_with_settlements'
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    policies = ('seeded_random', 'reconciliation', 'mark_all', 'oracle')
    def empty_totals():
        return {name: {'episodes': 0, 'tp': 0, 'fp': 0, 'fn': 0, 'f1_sum': 0.0, 'reward_sum': 0.0, 'inspection_steps_sum': 0} for name in policies}
    totals = empty_totals()
    splits = {split: empty_totals() for split in ('train', 'dev')}
    # Clean-only slices isolate false accusations from missed true faults.
    # Include them only for the opt-in mixed dataset; legacy reports stay stable.
    def empty_clean_slice():
        return {name: {'episodes': 0, 'false_accusation_episodes': 0, 'fp': 0,
                       'f1_sum': 0.0, 'reward_sum': 0.0} for name in policies}
    clean_slices = {'overall': {}, 'train': {}, 'dev': {}}
    model_counts = {'train': {}, 'dev': {}}
    trajectories = []
    seen_ids = set()
    for split in ('train', 'dev'):
        entries = index[split]
        if not isinstance(entries, list) or (index['kind'] in company_kinds and len(entries) != 10):
            raise ValueError('invalid index')
        for entry in entries:
            relative = entry['path']
            if not isinstance(relative, str) or not re.fullmatch(rf'{split}/episode-[0-9]{{2}}', relative):
                raise ValueError('invalid episode path')
            root = (dataset / relative).resolve(strict=True)
            if not root.is_relative_to(dataset):
                raise ValueError('episode outside dataset')
            public = load_public_episode(root / 'public')
            if public['manifest']['episode_id'] != entry['episode_id']:
                raise ValueError('index episode ID mismatch')
            if entry['episode_id'] in seen_ids:
                raise ValueError('repeated episode ID across dataset')
            seen_ids.add(entry['episode_id'])
            truth = json.loads((root / 'private' / 'truth.json').read_text(encoding='utf-8'))
            model = public['policy'].get('accounting_model')
            if index['kind'] in company_kinds:
                if model == 'accrual_company_v1':
                    from .company_checks import validate_company
                    validate_company(public, truth)
                elif extended and model == 'accrual_company_v2':
                    from .settlement_faults_v2 import validate_settlement_episode
                    validate_settlement_episode(public, truth)
                else:
                    raise ValueError('unsupported accounting model in development set')
            if extended:
                counts = model_counts[split]
                counts[model] = counts.get(model, 0) + 1
            public_ids = accessible_evidence_ids(public)
            for name in policies:
                result = run_baseline(public, truth, name, seed=0)
                score = result['score']
                inspection_steps = len(result['trajectory']) - 1 if result['trajectory'] is not None else 0
                for accumulator in (totals[name], splits[split][name]):
                    accumulator['episodes'] += 1
                    for metric in ('tp', 'fp', 'fn'):
                        accumulator[metric] += score[metric]
                    accumulator['f1_sum'] += score['f1']
                    accumulator['reward_sum'] += score['reward']
                    accumulator['inspection_steps_sum'] += inspection_steps
                if extended and not truth['issues']:
                    for label in ('overall', split):
                        measures = clean_slices[label].setdefault(model, empty_clean_slice())[name]
                        measures['episodes'] += 1
                        measures['fp'] += score['fp']
                        measures['false_accusation_episodes'] += int(score['fp'] > 0)
                        measures['f1_sum'] += score['f1']
                        measures['reward_sum'] += score['reward']
                if result['trajectory'] is not None:
                    env = LedgerSandbox(public, lambda answers, steps: evaluate(truth['issues'], answers, public_ids, steps))
                    replayed = replay_actions(env, result['trajectory'])['steps'][-1]
                    if not replayed[2] or replayed[3] or replayed[4].get('score') != score:
                        raise ValueError('trajectory replay did not reproduce the score')
                    trajectories.append({'episode_id': entry['episode_id'], 'split': split, 'policy': name,
                                         'trajectory_format': 'ledgergym-actions-v1', 'actions': result['trajectory']})
    for group in (totals, *splits.values()):
        for value in group.values():
            count = value['episodes']
            for metric in ('f1', 'reward', 'inspection_steps'):
                total = value.pop(metric + '_sum')
                value['mean_' + metric] = total / count if count else None
    summary = {'kind': index['kind'], 'policies': totals, 'splits': splits,
               'replay': {'trajectories': len(trajectories), 'score_matches': len(trajectories)}}
    if extended:
        for split in ('train', 'dev'):
            if model_counts[split].get('accrual_company_v2') != 2:
                raise ValueError('expected two clean settlement companies per split')
            if 'accrual_company_v1' not in clean_slices[split]:
                raise ValueError('expected at least one legacy clean control per split')
        for scope in clean_slices.values():
            for policy_slices in scope.values():
                for metrics in policy_slices.values():
                    n = metrics['episodes']
                    metrics['false_accusation_rate'] = metrics['false_accusation_episodes'] / n
                    metrics['mean_f1'] = metrics.pop('f1_sum') / n
                    metrics['mean_reward'] = metrics.pop('reward_sum') / n
        summary['model_counts'] = model_counts
        summary['clean_false_accusations'] = clean_slices
        summary['shortcut_warning'] = (
            'The public accrual_company_v2 model has both clean and faulted episodes, '
            'so model identity alone no longer predicts empty truth. Only two v2 '
            'cases per split: results are internal diagnostics, not statistical '
            'generalization or hidden evaluation.')
    (output / 'summary.json').write_text(json.dumps(summary, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    (output / 'trajectories.jsonl').write_text(''.join(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n' for record in trajectories), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description='Evaluate open development data and replay trajectories locally; not a hidden benchmark.')
    parser.add_argument('dataset')
    parser.add_argument('output', help='new report directory, must not already exist')
    args = parser.parse_args()
    result = evaluate_fixture_dataset(args.dataset, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
