import json
import subprocess
import sys


def test_offline_demo_executes_complete_episode():
    result = subprocess.run([sys.executable, '-m', 'ledgergym'], text=True, capture_output=True, check=True)
    report = json.loads(result.stdout)
    assert report['prototype'] is True
    assert report['terminated'] is True
    assert report['score']['tp'] == 1
    assert report['score']['fp'] == 0
    assert report['score']['fn'] == 0


def test_help_flags_print_usage_instead_of_running():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for command in ([sys.executable, '-m', 'ledgergym', '--help'],
                    [sys.executable, str(root / 'scripts' / 'verify_bundle.py'), '--help']):
        result = subprocess.run(command, text=True, capture_output=True, check=True, cwd=root)
        assert result.stdout.startswith('usage:')
        assert 'prototype' not in result.stdout


def test_judge_walkthrough_example_finds_all_planted_errors():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'examples' / 'judge_walkthrough.py')],
                            text=True, capture_output=True, check=True, cwd=root)
    last = result.stdout.strip().splitlines()[-1]
    assert 'TP 4  FP 0  FN 0' in last and 'F1 1.00' in last
    assert 'reward to agent=0.0  info={}' in result.stdout


def test_judge_walkthrough_detailed_shows_environment_and_attacks():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, str(root / 'examples' / 'judge_walkthrough.py'), '--detailed'],
                         text=True, capture_output=True, check=True, cwd=root).stdout
    for marker in ('── 1.', '── 2.', '── 3.', '── 4.', '── 5.', '── 6.'):
        assert marker in out
    assert "error 'invalid_action': only decimal arithmetic" in out
    assert 'TP 4  FP 0  FN 0' in out
    assert 'mark all (4 types x every invoice)   -> reward -1.000' in out
    assert 'silence on faulty books              -> reward -1.000' in out
