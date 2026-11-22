"""Agent diagnostics required by the FinTech case (section 10).

For every baseline policy: precision, recall, F1, episode return, inspection
steps and wall time, plus a measured failure breakdown (false negatives and
false positives per fault type, false accusations on clean episodes).

Runs on an existing development dataset (`--dataset`) and/or on freshly
generated held-out episodes (`--held-out N`): new seeds and parameter
combinations that are not part of the published 10+10 set.

Trusted, evaluator-side tool: it reads private truth. Never run it inside an
agent container. Wall time depends on hardware and is diagnostic only; it is
kept out of summary.json so the dataset stays byte-reproducible.
"""
import argparse
import json
from pathlib import Path
import time

from .baselines import run_baseline
from .episode_io import load_public_episode
from .score import accessible_evidence_ids, evaluate

POLICIES = ('seeded_random', 'reconciliation', 'mark_all', 'oracle')
FAULT_TYPES = ('duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period')

# Held-out combinations: seeds disjoint from the published set (2026 + i),
# sizes across the case range and the opt-in variation switches.
HELD_OUT_CONFIGS = (
    {'postings': 300, 'documents': 40, 'faults': {'duplicate_invoice': 1, 'reporting_period': 1}},
    {'postings': 1200, 'documents': 120, 'faults': {'payment_allocation': 2, 'fx_rate_or_date': 2},
     'compounds': {'fx_allocation': 1}},
    {'postings': 2000, 'documents': 200, 'faults': {'duplicate_invoice': 2, 'payment_allocation': 2,
     'fx_rate_or_date': 2, 'reporting_period': 2}, 'compounds': {'duplicate_allocation': 1, 'fx_allocation': 1}},
    {'postings': 600, 'documents': 60},
    {'postings': 800, 'documents': 100, 'faults': {'fx_rate_or_date': 2, 'duplicate_invoice': 2},
     'fault_parameters': 'varied', 'timestamp_offsets': 'mixed', 'evidence_alternatives': True},
    {'postings': 500, 'documents': 50, 'faults': {'payment_allocation': 3}, 'compounds': {'duplicate_allocation': 1},
     'fault_parameters': 'varied', 'timestamp_offsets': 'mixed'},
)


def _findings(result, truth, public_ids, policy):
    if policy == 'oracle':
        return [{'type': i['type'], 'affected_ids': i['affected_ids'],
                 'claimed_amount_minor': i['expected_amount_minor'], 'currency': i['currency'],
                 'evidence_ids': i['allowed_evidence_sets'][0], 'explanation': ''} for i in truth['issues']]
    last = result['trajectory'][-1] if result['trajectory'] else {}
    return last.get('findings', []) if last.get('action') == 'submit' else []


def _empty():
    return {'episodes': 0, 'tp': 0, 'fp': 0, 'fn': 0, 'precision_sum': 0.0, 'recall_sum': 0.0,
            'f1_sum': 0.0, 'return_sum': 0.0, 'steps_sum': 0, 'seconds_sum': 0.0,
            'clean_episodes': 0, 'clean_false_accusations': 0,
            'fn_by_type': {t: 0 for t in FAULT_TYPES}, 'fp_by_type': {},
            'truth_by_type': {t: 0 for t in FAULT_TYPES}}


def _add(acc, public, truth):
    public_ids = accessible_evidence_ids(public)
    for policy in POLICIES:
        started = time.perf_counter()
        result = run_baseline(public, truth, policy, seed=0)
        seconds = time.perf_counter() - started
        score = result['score']
        steps = len(result['trajectory']) - 1 if result['trajectory'] else 0
        row = acc[policy]
        row['episodes'] += 1
        for key in ('tp', 'fp', 'fn'):
            row[key] += score[key]
        row['precision_sum'] += score['precision']
        row['recall_sum'] += score['recall']
        row['f1_sum'] += score['f1']
        row['return_sum'] += score['reward']
        row['steps_sum'] += steps
        row['seconds_sum'] += seconds
        if not truth['issues']:
            row['clean_episodes'] += 1
            row['clean_false_accusations'] += int(score['fp'] > 0)
        # Matching requires equal types, so per-type scoring decomposes TP exactly.
        findings = _findings(result, truth, public_ids, policy)
        kinds = {i['type'] for i in truth['issues']} | {f.get('type') for f in findings}
        for kind in kinds:
            issues = [i for i in truth['issues'] if i['type'] == kind]
            claimed = [f for f in findings if f.get('type') == kind]
            part = evaluate(issues, claimed, public_ids, 0)
            if kind in row['truth_by_type']:
                row['truth_by_type'][kind] += len(issues)
                row['fn_by_type'][kind] += part['fn']
            if part['fp']:
                row['fp_by_type'][str(kind)] = row['fp_by_type'].get(str(kind), 0) + part['fp']


def _finish(acc):
    out = {}
    for policy, row in acc.items():
        n = row['episodes'] or 1
        out[policy] = {
            'episodes': row['episodes'], 'tp': row['tp'], 'fp': row['fp'], 'fn': row['fn'],
            # Micro-averaged over all findings/issues: per-episode P and R are 0 on
            # clean episodes by the case convention, which would distort a mean.
            'precision': round(row['tp'] / (row['tp'] + row['fp']), 4) if row['tp'] + row['fp'] else 0.0,
            'recall': round(row['tp'] / (row['tp'] + row['fn']), 4) if row['tp'] + row['fn'] else 0.0,
            'mean_episode_precision': round(row['precision_sum'] / n, 4),
            'mean_episode_recall': round(row['recall_sum'] / n, 4),
            'mean_f1': round(row['f1_sum'] / n, 4),
            'mean_return': round(row['return_sum'] / n, 4),
            'mean_steps': round(row['steps_sum'] / n, 2),
            'mean_seconds': round(row['seconds_sum'] / n, 4),
            'clean_episodes': row['clean_episodes'],
            'clean_false_accusation_episodes': row['clean_false_accusations'],
            'missed_by_type': {k: f"{row['fn_by_type'][k]}/{row['truth_by_type'][k]}" for k in FAULT_TYPES},
            'false_positives_by_claimed_type': dict(sorted(row['fp_by_type'].items())),
        }
    return out


def diagnose_dataset(dataset):
    root = Path(dataset)
    index = json.loads((root / 'index.json').read_text(encoding='utf-8'))
    acc = {p: _empty() for p in POLICIES}
    for split in ('train', 'dev'):
        for entry in index[split]:
            episode = root / entry['path']
            public = load_public_episode(episode / 'public')
            truth = json.loads((episode / 'private' / 'truth.json').read_text(encoding='utf-8'))
            _add(acc, public, truth)
    return _finish(acc)


def diagnose_held_out(count, first_seed=2026):
    from .company_world import build_company
    acc = {p: _empty() for p in POLICIES}
    for i in range(count):
        config = HELD_OUT_CONFIGS[i % len(HELD_OUT_CONFIGS)]
        public, truth, _ = build_company(first_seed + i, dict(config))
        _add(acc, public, truth)
    return _finish(acc)


def _table(title, report):
    lines = [f'### {title}', '',
             '| Policy | P (micro) | R (micro) | F1 (mean) | Return (mean) | Steps (mean) | Time, s (mean) | Clean episodes with false accusations | Missed (FN/total) by type |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for policy, r in report.items():
        missed = ', '.join(f'{k} {v}' for k, v in r['missed_by_type'].items())
        lines.append(f"| {policy} | {r['precision']:.2f} | {r['recall']:.2f} | {r['mean_f1']:.2f} | "
                     f"{r['mean_return']:.3f} | {r['mean_steps']:.1f} | {r['mean_seconds']:.3f} | "
                     f"{r['clean_false_accusation_episodes']}/{r['clean_episodes']} | {missed} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--dataset', help='existing development dataset with private truth')
    parser.add_argument('--held-out', type=int, default=0, metavar='N',
                        help='also generate N fresh episodes with unseen seeds/parameters')
    parser.add_argument('--json', help='write the full report to this new JSON file')
    args = parser.parse_args(argv)
    if not args.dataset and not args.held_out:
        parser.error('give --dataset and/or --held-out N')
    if args.held_out < 0 or args.held_out > 500:
        parser.error('--held-out must be 0..500')
    report = {'kind': 'ledgergym_agent_diagnostics_v1',
              'note': 'Trusted local diagnostics; wall time is hardware dependent; not a hidden benchmark.'}
    text = []
    if args.dataset:
        report['dataset'] = diagnose_dataset(args.dataset)
        text.append(_table('Published development set (10 train + 10 dev)', report['dataset']))
    if args.held_out:
        report['held_out'] = diagnose_held_out(args.held_out)
        report['held_out_episodes'] = args.held_out
        text.append(_table(f'Held-out episodes ({args.held_out}, unseen seeds and parameters)', report['held_out']))
    if args.json:
        with open(args.json, 'x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write('\n')
    print('\n'.join(text))


if __name__ == '__main__':
    main()
