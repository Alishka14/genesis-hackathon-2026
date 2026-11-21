import json
import subprocess
import sys

import pytest

from ledgergym.verification import run_test_suite, verify


@pytest.mark.parametrize('source, status, passed, failed, skipped', [
    ('def test_ok(): assert 2 + 2 == 4', 'PASS', 1, 0, 0),
    ('def test_bad(): assert False', 'FAIL', 0, 1, 0),
    ('import pytest\n@pytest.mark.skip(reason="unavailable")\ndef test_skip(): pass', 'PARTIAL', 0, 0, 1),
    ('# no tests', 'FAIL', 0, 0, 0),
    ('raise RuntimeError("collection failed")', 'FAIL', 0, 1, 0),
])
def test_actual_pytest_results_control_status(tmp_path, monkeypatch, source, status, passed, failed, skipped):
    suite = tmp_path / 'suite'
    suite.mkdir()
    (suite / 'test_sample.py').write_text(source)
    out = tmp_path / 'out'
    out.mkdir()
    # Inherited pytest arguments must not select away failures or redirect reports.
    monkeypatch.setenv('PYTEST_ADDOPTS', '-k nothing --junitxml=/unwanted-report.xml')
    result = run_test_suite(suite, out)
    assert result['status'] == status
    assert result['passed'] == passed and result['failed'] == failed and result['skipped'] == skipped
    assert (out / 'pytest.log').is_file() and (out / 'pytest.xml').is_file()


def test_pytest_timeout_is_an_explicit_failure(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(subprocess, 'run', timeout)
    result = run_test_suite(tmp_path, tmp_path, timeout=1)
    assert result['status'] == 'FAIL' and result['reason'] == 'pytest timeout'


def test_single_command_builds_dataset_events_and_report(tmp_path):
    suite = tmp_path / 'suite'
    suite.mkdir()
    (suite / 'test_sample.py').write_text('def test_ok(): assert True')
    out = tmp_path / 'verification'
    result = subprocess.run([sys.executable, '-m', 'ledgergym.verification', str(out), '--tests', str(suite)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / 'verification.json').read_text())
    assert report['status'] == 'PASS' and report['test_scope'] == 'custom'
    assert report['checks']['tests']['passed'] == 1
    assert report['checks']['dataset']['train'] == report['checks']['dataset']['dev'] == 10
    evaluation = report['checks']['evaluation']
    assert evaluation['trajectories'] == evaluation['score_matches'] == 60
    assert evaluation['resets'] == evaluation['terminals'] == 60
    assert evaluation['events'] > 120
    assert (out / 'dataset/train/episode-00/private/truth.json').is_file()
    assert (out / 'evaluation/events.jsonl').is_file()
    assert report['elapsed_seconds'] > 0
    repeated = subprocess.run([sys.executable, '-m', 'ledgergym.verification', str(out), '--tests', str(suite)], capture_output=True, text=True)
    assert repeated.returncode != 0 and 'already exists' in repeated.stderr
    assert json.loads((out / 'verification.json').read_text()) == report


@pytest.mark.parametrize('test_status, expected', [('FAIL', 'FAIL'), ('PARTIAL', 'PARTIAL')])
def test_nonpassing_tests_never_become_pass(tmp_path, monkeypatch, test_status, expected):
    import ledgergym.verification as module
    monkeypatch.setattr(module, 'run_test_suite', lambda *args, **kwargs: {'status': test_status})
    report = verify(tmp_path / 'output', tests=tmp_path)
    assert report['status'] == expected
    assert report['checks']['evaluation']['status'] == 'PASS'


def test_generator_failure_is_saved_and_stops_dependent_checks(tmp_path, monkeypatch):
    import ledgergym.verification as module
    monkeypatch.setattr(module, 'run_test_suite', lambda *args, **kwargs: {'status': 'PASS'})
    def fail(*args, **kwargs):
        raise ValueError('broken generator')
    monkeypatch.setattr(module, 'create_company_dataset', fail)
    report = verify(tmp_path / 'output', tests=tmp_path)
    assert report['status'] == 'FAIL'
    assert report['checks']['dataset']['status'] == 'FAIL'
    assert report['checks']['evaluation']['status'] == 'NOT_RUN'
    assert 'broken generator' in (tmp_path / 'output/verification.json').read_text()


@pytest.mark.parametrize('damage', ['missing', 'extra', 'action', 'private_field', 'terminal', 'episode'])
def test_artifact_checker_rejects_broken_or_overexposed_event_files(tmp_path, damage):
    from ledgergym.fixture_dataset import create_fixture_dataset
    from ledgergym.fixture_evaluation import evaluate_fixture_dataset
    from ledgergym.verification import check_event_artifacts
    create_fixture_dataset(tmp_path / 'data')
    evaluate_fixture_dataset(tmp_path / 'data', tmp_path / 'evaluation')
    path = tmp_path / 'evaluation/events.jsonl'
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if damage == 'missing':
        events.pop()
    elif damage == 'extra':
        events.append(events[-1])
    elif damage == 'action':
        events[1]['action'] = {'action': 'calculator', 'expression': '999'}
    elif damage == 'private_field':
        events[1]['info'] = {'secret': 'private-score'}
    elif damage == 'terminal':
        events[1]['terminated'] = True
    elif damage == 'episode':
        events[0]['observation']['manifest']['episode_id'] = 'another-episode'
    path.write_text(''.join(json.dumps(e) + '\n' for e in events))
    with pytest.raises(ValueError):
        check_event_artifacts(path.parent)
