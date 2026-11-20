"""Evaluate development fixtures locally. Not a secure or independent benchmark."""
import argparse
import json
from pathlib import Path
import re
from .baselines import run_baseline
from .episode_io import load_public_episode


def evaluate_fixture_dataset(dataset, output):
    """Trusted evaluator only: reads private truth. Never mount it into an agent."""
    dataset = Path(dataset).resolve(strict=True)
    index = json.loads((dataset / 'index.json').read_text(encoding='utf-8'))
    if index.get('kind') != 'development_fixtures_not_benchmark':
        raise ValueError('expected development fixtures')
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    policies = ('seeded_random', 'reconciliation', 'mark_all', 'oracle')
    totals = {name: {'episodes': 0, 'tp': 0, 'fp': 0, 'fn': 0, 'f1_sum': 0.0} for name in policies}
    trajectories = []
    for split in ('train', 'dev'):
        entries = index[split]
        if not isinstance(entries, list):
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
            truth = json.loads((root / 'private' / 'truth.json').read_text(encoding='utf-8'))
            for name in policies:
                result = run_baseline(public, truth, name, seed=0)
                score, totals_for_policy = result['score'], totals[name]
                totals_for_policy['episodes'] += 1
                for metric in ('tp', 'fp', 'fn'):
                    totals_for_policy[metric] += score[metric]
                totals_for_policy['f1_sum'] += score['f1']
                if result['trajectory'] is not None:
                    trajectories.append({'episode_id': entry['episode_id'], 'split': split, 'policy': name, 'actions': result['trajectory']})
    for value in totals.values():
        count = value['episodes']
        value['mean_f1'] = value.pop('f1_sum') / count if count else None
    summary = {'kind': index['kind'], 'policies': totals}
    (output / 'summary.json').write_text(json.dumps(summary, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    (output / 'trajectories.jsonl').write_text(''.join(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n' for record in trajectories), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description='Evaluate small development fixtures locally; not a benchmark.')
    parser.add_argument('dataset')
    parser.add_argument('output', help='new report directory, must not already exist')
    args = parser.parse_args()
    result = evaluate_fixture_dataset(args.dataset, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
