"""Evaluate open development datasets locally. Not a secure or independent benchmark."""
import argparse
import json
from pathlib import Path
import re
from .baselines import run_baseline
from .episode_io import load_public_episode
from .env import LedgerSandbox
from .event_recorder import public_events
from .replay import replay_actions
from .score import evaluate


def evaluate_fixture_dataset(dataset, output):
    """Trusted evaluator only: reads private truth. Never mount it into an agent."""
    dataset = Path(dataset).resolve(strict=True)
    index = json.loads((dataset / 'index.json').read_text(encoding='utf-8'))
    if index.get('kind') not in {'development_fixtures_not_benchmark', 'synthetic_company_development'}:
        raise ValueError('expected a supported development dataset')
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    policies = ('seeded_random', 'reconciliation', 'mark_all', 'oracle')
    def empty_totals():
        return {name: {'episodes': 0, 'tp': 0, 'fp': 0, 'fn': 0, 'f1_sum': 0.0, 'reward_sum': 0.0, 'inspection_steps_sum': 0} for name in policies}
    totals = empty_totals()
    splits = {split: empty_totals() for split in ('train', 'dev')}
    trajectories = []
    events = []
    seen_ids = set()
    for split in ('train', 'dev'):
        entries = index[split]
        if not isinstance(entries, list) or (index['kind'] == 'synthetic_company_development' and len(entries) != 10):
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
            if index['kind'] == 'synthetic_company_development':
                from .company_checks import validate_company
                validate_company(public, truth)
            public_ids = {v for rows in public['tables'].values() for row in rows for key, v in row.items()
                          if key.endswith('_id') and isinstance(v, str)}
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
                if result['trajectory'] is not None:
                    env = LedgerSandbox(public, lambda answers, steps: evaluate(truth['issues'], answers, public_ids, steps))
                    replay = replay_actions(env, result['trajectory'])
                    replayed = replay['steps'][-1]
                    if not replayed[2] or replayed[3] or replayed[4].get('score') != score:
                        raise ValueError('trajectory replay did not reproduce the score')
                    trajectories.append({'episode_id': entry['episode_id'], 'split': split, 'policy': name,
                                         'trajectory_format': 'ledgergym-actions-v1', 'actions': result['trajectory']})
                    events.extend(dict(event, split=split, policy=name)
                                  for event in public_events(result['trajectory'], replay))
    for group in (totals, *splits.values()):
        for value in group.values():
            count = value['episodes']
            for metric in ('f1', 'reward', 'inspection_steps'):
                total = value.pop(metric + '_sum')
                value['mean_' + metric] = total / count if count else None
    summary = {'kind': index['kind'], 'policies': totals, 'splits': splits,
               'replay': {'trajectories': len(trajectories), 'score_matches': len(trajectories)}}
    (output / 'summary.json').write_text(json.dumps(summary, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    (output / 'trajectories.jsonl').write_text(''.join(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n' for record in trajectories), encoding='utf-8')
    with (output / 'events.jsonl').open('w', encoding='utf-8') as stream:
        for event in events:
            stream.write(json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n')
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
