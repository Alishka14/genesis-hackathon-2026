"""Offline local checks: pytest, 10+10 company episodes, baselines and replay.

No downloads or installations. PASS covers these checks only, not all project gates.
The output contains private development labels and must stay evaluator-side.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from .company_dataset import create_company_dataset
from .fixture_evaluation import evaluate_fixture_dataset


def run_test_suite(tests, output, *, timeout=600):
    """Run the same package as this command, with ambient pytest options disabled."""
    output, tests = Path(output).resolve(), Path(tests).resolve()
    config = output / 'pytest.ini'
    config.write_text('[pytest]\n', encoding='utf-8')
    env = dict(os.environ)
    env.pop('PYTEST_ADDOPTS', None)
    env.pop('PYTEST_PLUGINS', None)
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
    command = [sys.executable, '-m', 'pytest', '-c', str(config), str(tests),
               '-q', '-rs', '--junitxml', str(output / 'pytest.xml')]
    with (output / 'pytest.log').open('w', encoding='utf-8') as log:
        try:
            result = subprocess.run(command, cwd=output, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': 'pytest timeout'}
        except OSError as exc:
            return {'status': 'FAIL', 'reason': str(exc)}
    try:
        cases = list(ET.parse(output / 'pytest.xml').getroot().iter('testcase'))
    except (OSError, ET.ParseError) as exc:
        return {'status': 'FAIL', 'returncode': result.returncode, 'reason': f'missing/invalid JUnit report: {exc}'}
    failed = sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
    skipped = sum(c.find('skipped') is not None for c in cases)
    passed = len(cases) - failed - skipped
    status = 'FAIL' if result.returncode != 0 or failed or not cases else 'PARTIAL' if skipped else 'PASS'
    return {'status': status, 'returncode': result.returncode, 'total': len(cases),
            'passed': passed, 'failed': failed, 'skipped': skipped}


def check_event_artifacts(output):
    """Check the exported event/action correspondence, including every reset/end."""
    output = Path(output)
    trajectories = [json.loads(line) for line in (output / 'trajectories.jsonl').read_text(encoding='utf-8').splitlines()]
    count = resets = terminals = 0
    seen = set()
    with (output / 'events.jsonl').open(encoding='utf-8') as stream:
        for trajectory in trajectories:
            identity = (trajectory['episode_id'], trajectory['policy'])
            if identity in seen or trajectory['policy'] == 'oracle':
                raise ValueError('duplicate or oracle trajectory')
            seen.add(identity)
            actions = trajectory['actions']
            if not actions:
                raise ValueError('empty baseline trajectory')
            for index, action in enumerate([None, *actions], start=-1):
                line = stream.readline()
                if not line:
                    raise ValueError('missing event')
                event = json.loads(line)
                expected_keys = {'event_format', 'episode_id', 'split', 'policy', 'step', 'action',
                                 'observation', 'reward', 'terminated', 'truncated'}
                if (set(event) != expected_keys or event['event_format'] != 'ledgergym-events-v1'
                        or any(event[k] != trajectory[k] for k in ('episode_id', 'split', 'policy'))
                        or event['step'] != index or event['action'] != action
                        or event['terminated'] is not (index == len(actions) - 1)
                        or event['truncated'] is not False):
                    raise ValueError('event does not match baseline trajectory')
                if index == -1:
                    if event['observation']['manifest']['episode_id'] != identity[0] or event['reward'] != 0:
                        raise ValueError('invalid reset event')
                    resets += 1
                terminals += int(event['terminated'])
                count += 1
        if stream.read():
            raise ValueError('extra events')
    if len(trajectories) != 60:
        raise ValueError('expected 60 baseline trajectories')
    hashes = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
              for name in ('summary.json', 'trajectories.jsonl', 'events.jsonl')}
    return {'events': count, 'resets': resets, 'terminals': terminals, 'sha256': hashes}


def verify(output, *, tests=None, seed=2026):
    """Create a NEW report directory; persist failures without overwriting evidence."""
    output = Path(output).resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    started = time.monotonic()
    default_tests = Path(__file__).resolve().parent.parent / 'tests'
    if not default_tests.is_dir():
        default_tests = Path.cwd() / 'tests'
    report = {'format': 'ledgergym-verification-v1', 'status': 'RUNNING',
              'test_scope': 'default' if tests is None else 'custom',
              'python': sys.version.split()[0], 'checks': {}}

    def save():
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (output / 'verification.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def check(name, function):
        begin = time.monotonic()
        try:
            value = function()
        except Exception as exc:
            value = {'status': 'FAIL', 'reason': f'{type(exc).__name__}: {exc}'}
        value['elapsed_seconds'] = round(time.monotonic() - begin, 3)
        report['checks'][name] = value
        save()
        return value

    save()
    check('tests', lambda: run_test_suite(default_tests if tests is None else tests, output))

    def dataset():
        index = create_company_dataset(output / 'dataset', seed=seed)
        if len(index['train']) != 10 or len(index['dev']) != 10:
            raise ValueError('expected 10 train + 10 dev')
        return {'status': 'PASS', 'train': 10, 'dev': 10, 'kind': index['kind']}

    generated = check('dataset', dataset)

    def evaluation():
        summary = evaluate_fixture_dataset(output / 'dataset', output / 'evaluation')
        if (summary['replay'] != {'trajectories': 60, 'score_matches': 60}
                or set(summary['policies']) != {'seeded_random', 'reconciliation', 'mark_all', 'oracle'}
                or any(v['episodes'] != 20 for v in summary['policies'].values())):
            raise ValueError('incomplete baseline evaluation')
        return {'status': 'PASS', **summary['replay'], **check_event_artifacts(output / 'evaluation')}

    if generated['status'] == 'PASS':
        check('evaluation', evaluation)
    else:
        report['checks']['evaluation'] = {'status': 'NOT_RUN', 'reason': 'dataset generation failed'}
    statuses = {c['status'] for c in report['checks'].values()}
    report['status'] = 'FAIL' if statuses & {'FAIL', 'NOT_RUN'} else 'PARTIAL' if 'PARTIAL' in statuses else 'PASS'
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', help='new directory for reports and development data')
    parser.add_argument('--tests', type=Path, help='custom pytest path; report explicitly marks custom scope')
    parser.add_argument('--seed', type=int, default=2026, help='trusted development dataset seed')
    args = parser.parse_args()
    if Path(args.output).exists():
        parser.error('output already exists')
    report = verify(args.output, tests=args.tests, seed=args.seed)
    print(json.dumps(report, sort_keys=True))
    return {'PASS': 0, 'FAIL': 1, 'PARTIAL': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
