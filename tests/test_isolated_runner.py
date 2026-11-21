"""Container integration checks use only a locally available pinned image."""
import shutil
import subprocess
import pytest
from ledgergym.isolated_runner import run_isolated_agent, IMAGE
from ledgergym.world import make_episode


def _image_available():
    if not shutil.which('docker'):
        return False
    try:
        return subprocess.run(['docker', 'image', 'inspect', IMAGE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _image_available(), reason='pinned Docker image not locally available')


def test_isolated_agent_cannot_access_private_host_data_or_network(tmp_path):
    secret = tmp_path / 'secret.txt'
    secret.write_text('host-secret-token')
    script = tmp_path / 'agent.py'
    script.write_text('''import json, os, socket, sys\nfirst=json.loads(sys.stdin.readline())\nsecret_path=%r\ntry:\n    open(secret_path).read(); disk="leak"\nexcept OSError: disk="blocked"\ns=socket.socket(); s.settimeout(1)\ntry:\n    s.connect(("8.8.8.8",53)); network="leak"\nexcept OSError: network="blocked"\ntry:\n    open("/marker","w").write("x"); root="writable"\nexcept OSError: root="readonly"\nsock="socket" if os.path.exists("/var/run/docker.sock") else "no-socket"\nprint(json.dumps({"action":"get_record","table":"ledger","id":disk+":"+network+":"+root+":"+sock}),flush=True)\nsys.stdin.readline()\nprint(json.dumps({"action":"submit","episode_id":first["observation"]["manifest"]["episode_id"],"findings":[]}),flush=True)\n''' % str(secret))
    public, truth = make_episode(5, fault=False)
    result = run_isolated_agent(public, truth, script, timeout=15)
    assert result['outcome'] == 'terminated'
    assert result['score']['f1'] == 1
    assert result['actions'][0]['id'] == 'blocked:blocked:readonly:no-socket'
    assert 'host-secret-token' not in repr(result)


def test_isolated_runner_times_out_and_cleans_container(tmp_path):
    script = tmp_path / 'agent.py'
    script.write_text('import time\ntime.sleep(60)\n')
    public, truth = make_episode(5, fault=False)
    result = run_isolated_agent(public, truth, script, timeout=5)
    assert result['outcome'] == 'timeout'
    running = subprocess.check_output(['docker', 'ps', '-a', '--filter', 'name=ledgergym-agent-', '--format', '{{.Names}}'], text=True)
    assert not running.strip()


def test_isolated_runner_rejects_oversized_output(tmp_path):
    script = tmp_path / 'agent.py'
    script.write_text('import sys\nsys.stdin.readline()\nprint("x" * 70000, flush=True)\n')
    public, truth = make_episode(5, fault=False)
    result = run_isolated_agent(public, truth, script, timeout=15)
    assert result['outcome'] == 'protocol_error'


def test_isolated_runner_rejects_excessive_json_nesting(tmp_path):
    script = tmp_path / 'agent.py'
    script.write_text('import sys\nsys.stdin.readline()\nprint("[" * 2000 + "]" * 2000, flush=True)\n')
    public, truth = make_episode(5, fault=False)
    result = run_isolated_agent(public, truth, script, timeout=15)
    assert result['outcome'] == 'protocol_error'


def test_protocol_failure_does_not_claim_a_clean_score(tmp_path):
    script = tmp_path / 'agent.py'
    script.write_text('import sys\nsys.stdin.readline()\nprint("not json", flush=True)\n')
    public, truth = make_episode(5, fault=False)
    result = run_isolated_agent(public, truth, script, timeout=15)
    assert result['outcome'] == 'protocol_error'
    assert result['score'] is None


def test_isolated_agent_investigates_and_submits_without_hidden_reward(tmp_path):
    script = tmp_path / 'agent.py'
    script.write_text('''import json, sys\ndef receive():\n    e = json.loads(sys.stdin.readline())\n    assert e['reward'] == 0 and e['info'] == {}\n    assert 'truth' not in json.dumps(e)\n    return e['observation']\ndef action(value):\n    print(json.dumps(value), flush=True)\ninitial = receive()\naction({'action':'list_records','table':'invoices','limit':50})\ninvoices = receive()['records']\naction({'action':'list_records','table':'ledger','limit':50})\nrows = receive()['records']\na,b = invoices\nfinding={'type':'duplicate_invoice','affected_ids':[a['invoice_id'],b['invoice_id']], 'claimed_amount_minor':b['total_minor'],'currency':b['currency'],'evidence_ids':[a['doc_id'],b['doc_id']]+[r['row_id'] for r in rows if r['account']=='expense'],'explanation':''}\naction({'action':'submit','episode_id':initial['manifest']['episode_id'],'findings':[finding]})\n''')
    public, truth = make_episode(22, fault=True)
    result = run_isolated_agent(public, truth, script, timeout=15)
    assert result['outcome'] == 'terminated'
    assert result['score']['tp'] == 1 and result['score']['reward'] == .996
    assert 'private-' not in repr(result['actions'])


def test_isolated_agent_reads_maximum_company_through_paginated_tools(tmp_path):
    from ledgergym.company_world import build_company
    public, truth, _ = build_company(42, {'postings': 2000, 'documents': 200})
    script = tmp_path / 'agent.py'
    script.write_text('''import json, sys
def receive():
    message = json.loads(sys.stdin.readline())
    assert message['reward'] == 0 and message['info'] == {}
    assert not message['terminated'] and not message['truncated']
    return message['observation']
def send(action):
    print(json.dumps(action), flush=True)
initial = receive()
totals = {}
for table in ('ledger', 'invoices', 'payments', 'fx'):
    total = 0
    cursor = None
    while True:
        action = {'action': 'list_records', 'table': table, 'limit': 50}
        if cursor is not None:
            action['cursor'] = cursor
        send(action)
        page = receive()
        total += len(page['records'])
        cursor = page['next_cursor']
        if cursor is None:
            break
    totals[table] = total
assert totals['ledger'] == 2000
assert totals['invoices'] + totals['payments'] == 200
assert totals['fx'] == 29
send({'action': 'submit', 'episode_id': initial['manifest']['episode_id'], 'findings': []})
''')
    result = run_isolated_agent(public, truth, script, timeout=30)
    assert result['outcome'] == 'terminated'
    assert result['score']['f1'] == 1
    assert len(result['actions']) == 47
    assert result['score']['reward'] == pytest.approx(1 - .002 * 46)
