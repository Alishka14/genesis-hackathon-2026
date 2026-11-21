"""Fail-closed export of public 10+10 episodes and seven-field development traces.

This is an export of OPEN development data, never of evaluator-private truth.
Requires a generated-and-evaluated company dataset. No source files are changed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

PUBLIC_FILES = (
    'manifest.json', 'policy.json', 'ledger.csv', 'invoices.jsonl',
    'payments.jsonl', 'fx.csv',
)
EVENT_KEYS = frozenset({
    'episode_id', 'step', 'action', 'observation', 'reward',
    'terminated', 'truncated',
})
PRIVATE_KEYS = frozenset({
    'truth', 'provenance', 'seed', 'issue_id', 'allowed_evidence_sets',
    'expected_amount_minor', 'interventions', 'private_pair_index',
})
POLICIES = frozenset({'seeded_random', 'reconciliation', 'mark_all'})
KINDS = frozenset({
    'synthetic_company_development',
    'synthetic_company_development_with_settlements',
})


def _load_json(path: Path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'missing or linked input: {path.name}')
    return json.loads(path.read_text(encoding='utf-8'))


def _check_private_keys(value):
    if isinstance(value, dict):
        if PRIVATE_KEYS.intersection(value):
            raise ValueError('private evaluator key found in shareable data')
        for item in value.values():
            _check_private_keys(item)
    elif isinstance(value, list):
        for item in value:
            _check_private_keys(item)


def _read_lines(path: Path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'missing or linked input: {path.name}')
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip()]


def _validate_index(dataset: Path):
    index = _load_json(dataset / 'index.json')
    if (not isinstance(index, dict) or set(index) != {'kind', 'train', 'dev'}
            or index.get('kind') not in KINDS):
        raise ValueError('expected evaluated 10+10 company dataset')
    known = set()
    for split in ('train', 'dev'):
        entries = index.get(split)
        if not isinstance(entries, list) or len(entries) != 10:
            raise ValueError('expected exactly ten episodes per split')
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'path', 'episode_id'}:
                raise ValueError('invalid index entry')
            relative, episode_id = entry['path'], entry['episode_id']
            if not isinstance(relative, str) or not re.fullmatch(
                    rf'{split}/episode-[0-9]{{2}}', relative):
                raise ValueError('invalid relative episode path')
            if not isinstance(episode_id, str) or not episode_id or episode_id in known:
                raise ValueError('invalid or duplicate episode ID')
            known.add(episode_id)
            public_dir = dataset / relative / 'public'
            if not public_dir.is_dir() or public_dir.is_symlink():
                raise ValueError('missing or linked public directory')
            for name in PUBLIC_FILES:
                path = public_dir / name
                if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(dataset):
                    raise ValueError('missing, linked, or outside public file')
            manifest = _load_json(public_dir / 'manifest.json')
            if manifest.get('episode_id') != episode_id:
                raise ValueError('episode ID mismatch')
            _check_private_keys(manifest)
            _check_private_keys(_load_json(public_dir / 'policy.json'))
            for name in ('ledger.csv', 'fx.csv'):
                with (public_dir / name).open(encoding='utf-8', newline='') as stream:
                    headers = csv.DictReader(stream).fieldnames
                if not headers or PRIVATE_KEYS.intersection(headers):
                    raise ValueError('private evaluator column in public CSV')
            for name in ('invoices.jsonl', 'payments.jsonl'):
                for record in _read_lines(public_dir / name):
                    _check_private_keys(record)
    return index


def _validate_traces(dataset: Path, index: dict):
    submission = dataset / 'evaluation' / 'submission'
    if (not submission.is_dir() or submission.is_symlink()
            or (dataset / 'evaluation').is_symlink()
            or not submission.resolve().is_relative_to(dataset)):
        raise ValueError('full submission trace directory missing or linked')
    trace_index = _load_json(submission / 'trace_index.json')
    if (not isinstance(trace_index, dict)
            or trace_index.get('closed_mode') is not False
            or trace_index.get('private_truth_exported') is not False):
        raise ValueError('unexpected submission trace trust mode')
    if set(trace_index) != {'format', 'closed_mode', 'private_truth_exported', 'trajectories'}:
        raise ValueError('unexpected submission trace index fields')
    _check_private_keys(trace_index)
    spans = trace_index.get('trajectories')
    events = _read_lines(submission / 'trajectories.jsonl')
    if not isinstance(spans, list) or len(spans) != 60 or not events:
        raise ValueError('expected 60 non-oracle trajectories')
    episodes = {entry['episode_id']: split for split in ('train', 'dev')
                for entry in index[split]}
    seen = set()
    cursor = 0
    for span in spans:
        if not isinstance(span, dict) or set(span) != {'episode_id', 'split', 'policy', 'first_line', 'steps'}:
            raise ValueError('invalid trace index')
        episode_id, split, policy = (span.get('episode_id'),
                                     span.get('split'), span.get('policy'))
        steps, first_line = span.get('steps'), span.get('first_line')
        label = (episode_id, policy)
        if (episode_id not in episodes or split != episodes[episode_id]
                or policy not in POLICIES or label in seen
                or type(steps) is not int or steps < 1
                or type(first_line) is not int or first_line != cursor + 1):
            raise ValueError('invalid or incomplete trace index')
        seen.add(label)
        if cursor + steps > len(events):
            raise ValueError('trajectory references missing events')
        for step, event in enumerate(events[cursor:cursor + steps], 1):
            if (not isinstance(event, dict) or set(event) != EVENT_KEYS
                    or event['episode_id'] != episode_id
                    or type(event['step']) is not int or event['step'] != step
                    or not isinstance(event['action'], dict)
                    or not isinstance(event['observation'], dict)
                    or type(event['reward']) not in (int, float)
                    or type(event['terminated']) is not bool
                    or type(event['truncated']) is not bool
                    or event['truncated'] is True
                    or event['terminated'] is not (step == steps)):
                raise ValueError('invalid full seven-field trajectory event')
            _check_private_keys(event)
        cursor += steps
    if cursor != len(events) or len(seen) != 60:
        raise ValueError('incomplete trajectory coverage')
    return submission


def export_submission(dataset, destination):
    """Copy only explicitly permitted files into a newly created directory.

    Reject ambiguous/missing content and symlinks. Private evaluator folders are
    never enumerated or copied. Never claim closed-mode test certification.
    """
    dataset = Path(dataset).expanduser().resolve(strict=True)
    if not dataset.is_dir():
        raise ValueError('dataset must be a directory')
    destination = Path(destination).expanduser().absolute()
    parent = destination.parent.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('destination exists: choose a new path')
    if parent == dataset or parent.is_relative_to(dataset):
        raise ValueError('export must be outside input dataset')
    index = _validate_index(dataset)
    traces = _validate_traces(dataset, index)

    stage = Path(tempfile.mkdtemp(prefix='.ledgergym-submit-', dir=parent))
    try:
        shutil.copyfile(dataset / 'index.json', stage / 'index.json')
        for split in ('train', 'dev'):
            for entry in index[split]:
                relative = Path(entry['path'])
                source = dataset / relative / 'public'
                target = stage / relative / 'public'
                target.mkdir(parents=True)
                for name in PUBLIC_FILES:
                    shutil.copyfile(source / name, target / name)
        shutil.copyfile(traces / 'trajectories.jsonl', stage / 'trajectories.jsonl')
        shutil.copyfile(traces / 'trace_index.json', stage / 'trace_index.json')
        readme = (
            '# LedgerGym — public development submission data\n\n'
            '20 synthetic episodes (10 train, 10 dev). Each episode contains\n'
            'six public-only files in public/. No private/truth.json or\n'
            'private/provenance.json is included.\n\n'
            'trajectories.jsonl contains the required seven fields, including\n'
            'development-mode reward. It must not be provided as feedback in\n'
            'closed-mode agent evaluation. trace_index.json identifies the 60\n'
            'non-oracle baseline trajectories. The main source repository holds\n'
            'the generator, evaluator, tests and baseline implementations.\n\n'
            'This is an open, synthetic development dataset, not a blinded test\n'
            'or official contest certification. See SHA256SUMS.json.\n'
        )
        (stage / 'README_SUBMISSION.md').write_text(readme, encoding='utf-8')
        manifest = {}
        for file in sorted(stage.rglob('*')):
            if file.is_file():
                manifest[file.relative_to(stage).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        (stage / 'SHA256SUMS.json').write_text(
            json.dumps({'schema': 'ledgergym-public-submission-v1',
                        'files': manifest}, sort_keys=True, indent=2) + '\n',
            encoding='utf-8')
        # Audit the staged, allowlisted artifact before publishing it.
        # Support both `python scripts/export_submission.py` and package imports.
        if __package__:
            from .verify_submission_package import verify_public_package
        else:
            from verify_submission_package import verify_public_package
        verification = verify_public_package(stage)
        if verification['trajectories'] != 60:
            raise ValueError('incomplete public package verification')
        if destination.exists():
            raise FileExistsError('destination exists: choose a new path')
        os.rename(stage, destination)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {'status': 'exported_public_development_data',
            'train': 10, 'dev': 10, 'trajectories': 60,
            'exported_files': len(manifest) + 1,
            'destination': str(destination),
            'contest_certified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', help='evaluated 10+10 dataset directory')
    parser.add_argument('destination', help='NEW public-only export directory')
    args = parser.parse_args()
    print(json.dumps(export_submission(args.dataset, args.destination), sort_keys=True))


if __name__ == '__main__':
    main()
