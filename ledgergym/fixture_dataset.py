"""Generate 20 small reproducible development fixtures, not a benchmark."""
import argparse
import json
from pathlib import Path
import random
from .episode_io import export_episode
from .generator import generate_episode


def create_fixture_dataset(root):
    """Create a new directory, keeping public/ and private/ separate per item.

    The contents are intentionally small, deterministic and unsuitable for
    hidden scoring. Filesystem access separation must be provided externally.
    """
    root = Path(root)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    plan = [
        {'scenario': 'duplicate_invoice', 'fault': False},
        {'scenario': 'duplicate_invoice', 'fault': True},
        {'scenario': 'payment_allocation', 'fault': False},
        {'scenario': 'payment_allocation', 'fault': True},
        {'scenario': 'fx_rate_or_date', 'fault': False},
        {'scenario': 'fx_rate_or_date', 'fault': True},
        {'scenario': 'reporting_period', 'fault': False},
        {'scenario': 'reporting_period', 'fault': True},
        {'scenario': 'fx_allocation'},
        {'scenario': 'duplicate_allocation'},
    ]
    index = {'kind': 'development_fixtures_not_benchmark', 'train': [], 'dev': []}
    for split, base_seed in [('train', 1000), ('dev', 2000)]:
        split_dir = root / split
        split_dir.mkdir(mode=0o700)
        ordered = list(plan)
        random.Random(base_seed).shuffle(ordered)
        for number, config in enumerate(ordered):
            seed = base_seed + number
            public, truth = generate_episode(seed, config)
            relative = f'{split}/episode-{number:02}'
            export_episode(root / relative, public, truth, seed=seed)
            index[split].append({'path': relative, 'episode_id': public['manifest']['episode_id']})
    (root / 'index.json').write_text(json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    return index


def main():
    parser = argparse.ArgumentParser(description='Create 20 small development fixtures; not a benchmark.')
    parser.add_argument('output', help='new directory, must not already exist')
    args = parser.parse_args()
    index = create_fixture_dataset(args.output)
    print(json.dumps({'kind': index['kind'], 'train': len(index['train']), 'dev': len(index['dev'])}, sort_keys=True))


if __name__ == '__main__':
    main()
