"""Submission export must never include private truth, oracle or malformed traces."""
import hashlib
import json

import pytest

from scripts.export_submission import export_submission


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def _fixture(root):
    root.mkdir()
    index = {'kind': 'synthetic_company_development_with_settlements', 'train': [], 'dev': []}
    events, spans = [], []
    for split in ('train', 'dev'):
        for n in range(10):
            eid = f'{split}-{n:02}'
            rel = f'{split}/episode-{n:02}'
            index[split].append({'path': rel, 'episode_id': eid})
            pub = root / rel / 'public'
            priv = root / rel / 'private'
            pub.mkdir(parents=True)
            priv.mkdir()
            _write_json(pub / 'manifest.json', {'episode_id': eid})
            _write_json(pub / 'policy.json', {'accounting_model': 'accrual_company_v1'})
            (pub / 'ledger.csv').write_text('row_id\n1\n')
            (pub / 'fx.csv').write_text('rate_id\n1\n')
            (pub / 'invoices.jsonl').write_text('{}\n')
            (pub / 'payments.jsonl').write_text('{}\n')
            _write_json(priv / 'truth.json', {'issues': [{'issue_id': 'secret'}]})
            _write_json(priv / 'provenance.json', {'seed': 123})
            for name in ('seeded_random', 'reconciliation', 'mark_all'):
                spans.append({'episode_id': eid, 'split': split, 'policy': name,
                              'first_line': len(events) + 1, 'steps': 2})
                for step in (1, 2):
                    events.append({'episode_id': eid, 'step': step,
                                   'action': {'name': 'submit' if step == 2 else 'list_records'},
                                   'observation': {'remaining_steps': 100 - step},
                                   'reward': 0.0, 'terminated': step == 2,
                                   'truncated': False})
    _write_json(root / 'index.json', index)
    traces = root / 'evaluation' / 'submission'
    traces.mkdir(parents=True)
    _write_json(traces / 'trace_index.json',
                {'closed_mode': False, 'private_truth_exported': False,
                 'trajectories': spans})
    (traces / 'trajectories.jsonl').write_text(
        ''.join(json.dumps(event) + '\n' for event in events))
    return traces


def test_public_export_no_secret_and_hashes(tmp_path):
    source = tmp_path / 'source'
    _fixture(source)
    output = tmp_path / 'public-submission'
    result = export_submission(source, output)
    assert result['train'] == result['dev'] == 10
    assert result['trajectories'] == 60
    assert result['contest_certified'] is False
    assert len(list(output.rglob('public'))) == 20
    for rel in output.rglob('*'):
        assert 'private' not in rel.parts
    assert not list(output.rglob('truth.json'))
    assert not list(output.rglob('provenance.json'))
    assert len(list(output.rglob('manifest.json'))) == 20
    assert len((output / 'trajectories.jsonl').read_text().splitlines()) == 120
    sums = json.loads((output / 'SHA256SUMS.json').read_text())['files']
    for rel, digest in sums.items():
        assert hashlib.sha256((output / rel).read_bytes()).hexdigest() == digest
    assert result['exported_files'] == len(sums) + 1
    with pytest.raises(FileExistsError):
        export_submission(source, output)


def test_private_field_in_observation_rejected_without_output(tmp_path):
    src = tmp_path / 'source'
    traces = _fixture(src)
    lines = (traces / 'trajectories.jsonl').read_text().splitlines()
    event = json.loads(lines[0])
    event['observation']['provenance'] = {'seed': 123}
    lines[0] = json.dumps(event)
    (traces / 'trajectories.jsonl').write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError, match='private evaluator'):
        export_submission(src, tmp_path / 'result')
    assert not (tmp_path / 'result').exists()


def test_missing_trajectory_and_symlink_rejected(tmp_path):
    src = tmp_path / 'source'
    traces = _fixture(src)
    output = tmp_path / 'result'
    lines = (traces / 'trajectories.jsonl').read_text().splitlines()
    (traces / 'trajectories.jsonl').write_text('\n'.join(lines[:-1]) + '\n')
    with pytest.raises(ValueError, match='missing events'):
        export_submission(src, output)
    assert not output.exists()
    (traces / 'trajectories.jsonl').write_text('\n'.join(lines) + '\n')
    path = src / 'train' / 'episode-00' / 'public' / 'ledger.csv'
    path.unlink()
    path.symlink_to(src / 'train' / 'episode-00' / 'private' / 'truth.json')
    with pytest.raises(ValueError, match='linked'):
        export_submission(src, output)
    assert not output.exists()


def test_outside_and_missing_episodes_rejected(tmp_path):
    src = tmp_path / 'source'
    _fixture(src)
    with pytest.raises(ValueError, match='outside input'):
        export_submission(src, src / 'export')
    index = json.loads((src / 'index.json').read_text())
    index['train'][0]['path'] = '../private'
    _write_json(src / 'index.json', index)
    with pytest.raises(ValueError, match='relative episode path'):
        export_submission(src, tmp_path / 'export')
