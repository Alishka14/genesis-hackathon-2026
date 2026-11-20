"""Build an open 10+10 synthetic company development set, using only stdlib."""
import argparse
import json
from pathlib import Path
import random
from .company_world import build_company
from .episode_io import export_episode


def create_company_dataset(root, *, seed=2026):
    """Create reproducible data in a NEW directory; private labels stay separate.

    This intentionally published development set is not a hidden benchmark.
    Directory separation does not isolate untrusted agent processes.
    """
    if type(seed) is not int:
        raise ValueError('dataset seed must be an integer')
    root = Path(root)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    rng = random.Random(f'company-dataset-0.1:{seed}')
    plans = [{}, *[{'faults': {kind: 1}} for kind in
                  ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')],
             {'compounds': {'fx_allocation': 1}}, {'compounds': {'duplicate_allocation': 1}},
             {'faults': {kind: 1 for kind in ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')}},
             {'faults': {kind: 2 for kind in ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')},
              'compounds': {'fx_allocation': 1, 'duplicate_allocation': 1}}, {}]
    sizes = [(200, 20), (320, 40), (460, 60), (620, 80), (800, 80),
             (980, 100), (1200, 120), (1450, 140), (1700, 180), (2000, 200)]
    index = {'kind': 'synthetic_company_development', 'train': [], 'dev': []}
    used_seeds, used_ids = set(), set()
    for split in ('train', 'dev'):
        (root / split).mkdir(mode=0o700)
        shuffled_plans, shuffled_sizes = list(plans), list(sizes)
        rng.shuffle(shuffled_plans)
        rng.shuffle(shuffled_sizes)
        for number, (plan, size) in enumerate(zip(shuffled_plans, shuffled_sizes)):
            postings, documents = size
            # The twelve-fault mix needs ten disjoint business operations.
            if sum(plan.get('faults', {}).values()) + 2 * sum(plan.get('compounds', {}).values()) == 12:
                documents = max(documents, 40)
            episode_seed = rng.getrandbits(128)
            while episode_seed in used_seeds:
                episode_seed = rng.getrandbits(128)
            used_seeds.add(episode_seed)
            public, truth, provenance = build_company(episode_seed, {'postings': postings, 'documents': documents, **plan})
            episode_id = public['manifest']['episode_id']
            if episode_id in used_ids:
                raise ValueError('duplicate episode ID')
            used_ids.add(episode_id)
            relative = f'{split}/episode-{number:02}'
            export_episode(root / relative, public, truth, seed=episode_seed, provenance=provenance)
            index[split].append({'path': relative, 'episode_id': episode_id})
    (root / 'index.json').write_text(json.dumps(index, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    return index


def main():
    parser = argparse.ArgumentParser(description='Create 10 train + 10 dev company histories; open development data, not a hidden benchmark.')
    parser.add_argument('output', help='new directory, must not already exist')
    parser.add_argument('--seed', type=int, default=2026, help='trusted dataset seed, never written into public index')
    parser.add_argument('--evaluate', action='store_true', help='run four trusted baselines and verify portable trajectories offline')
    args = parser.parse_args()
    index = create_company_dataset(args.output, seed=args.seed)
    result = {'kind': index['kind'], 'train': len(index['train']), 'dev': len(index['dev'])}
    if args.evaluate:
        from .fixture_evaluation import evaluate_fixture_dataset
        report = evaluate_fixture_dataset(args.output, Path(args.output) / 'evaluation')
        result['replay'] = report['replay']
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
