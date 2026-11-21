"""Tiny example agent for duplicate fixtures; not a general auditor."""
import json
import sys


def receive():
    return json.loads(sys.stdin.readline())['observation']


def act(action):
    print(json.dumps(action, separators=(',', ':')), flush=True)


initial = receive()
act({'action': 'list_records', 'table': 'invoices', 'limit': 50})
invoices = receive()['records']
act({'action': 'list_records', 'table': 'ledger', 'limit': 50})
rows = receive()['records']
findings = []
if len(invoices) == 2:
    first, second = invoices
    a, b = first['line_items'][0], second['line_items'][0]
    if a.get('service_ref') and a.get('service_ref') == b.get('service_ref') and first['entity_id'] == second['entity_id']:
        ids = [first['invoice_id'], second['invoice_id']]
        matching = [row['row_id'] for row in rows if row['account'] == 'expense' and row['invoice_id'] in ids]
        if len(matching) == 2:
            findings.append({'type': 'duplicate_invoice', 'affected_ids': ids, 'claimed_amount_minor': second['total_minor'], 'currency': second['currency'], 'evidence_ids': [first['doc_id'], second['doc_id'], *matching], 'explanation': ''})
act({'action': 'submit', 'episode_id': initial['manifest']['episode_id'], 'findings': findings})
