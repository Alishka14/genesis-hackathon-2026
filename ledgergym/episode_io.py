"""Deterministic local fixture interchange; directories do not isolate agents."""
import csv
import json
from pathlib import Path
from .world import validate_episode
from .payment_world import validate_payment_episode
from .fx_world import validate_fx_episode
from .period_world import validate_period_episode


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _validator(public):
    tables = public['tables']
    if tables['fx']:
        return validate_fx_episode
    if any('reporting_period' in row for row in tables['ledger']):
        return validate_period_episode
    if tables['payments']:
        return validate_payment_episode
    return validate_episode


def export_episode(root, public, truth, *, seed):
    """Create a new folder with public/ and private/; never overwrite an episode.

    Both folders are readable to a process with access to their parent. Do not
    expose the parent to an untrusted agent. Real isolation remains unimplemented.
    """
    _validator(public)(public, truth)
    root = Path(root)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    pub, private = root / 'public', root / 'private'
    pub.mkdir(mode=0o700)
    private.mkdir(mode=0o700)
    for filename, value in [('manifest.json', public['manifest']), ('policy.json', public['policy'])]:
        (pub / filename).write_text(_json_text(value) + '\n', encoding='utf-8')
    for table in ('invoices', 'payments'):
        (pub / f'{table}.jsonl').write_text(''.join(_json_text(row) + '\n' for row in public['tables'][table]), encoding='utf-8')
    columns = {'ledger': ['row_id', 'timestamp', 'account', 'debit_minor', 'credit_minor', 'currency', 'entity_id', 'invoice_id', 'payment_id'], 'fx': ['rate_id', 'date', 'source_currency', 'target_currency', 'rate']}
    for table in ('ledger', 'fx'):
        records = public['tables'][table]
        fields = columns[table] + sorted({key for row in records for key in row} - set(columns[table]))
        with (pub / f'{table}.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(records)
    (private / 'truth.json').write_text(_json_text(truth) + '\n', encoding='utf-8')
    (private / 'provenance.json').write_text(_json_text({'seed': seed, 'generator_version': '0.2-fixture'}) + '\n', encoding='utf-8')


def load_public_episode(public_dir):
    """Load only the explicitly provided public folder; never read private/."""
    folder = Path(public_dir)
    public = {key: json.loads((folder / f'{key}.json').read_text(encoding='utf-8')) for key in ('manifest', 'policy')}
    tables = {}
    for table in ('invoices', 'payments'):
        text = (folder / f'{table}.jsonl').read_text(encoding='utf-8')
        tables[table] = [json.loads(line) for line in text.splitlines() if line]
    for table in ('ledger', 'fx'):
        with (folder / f'{table}.csv').open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        if table == 'ledger':
            for row in rows:
                for key in ('debit_minor', 'credit_minor'):
                    row[key] = int(row[key])
                for key in ('invoice_id', 'payment_id'):
                    if row[key] == '':
                        row[key] = None
        tables[table] = rows
    public['tables'] = tables
    return public
