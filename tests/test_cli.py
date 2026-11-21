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
