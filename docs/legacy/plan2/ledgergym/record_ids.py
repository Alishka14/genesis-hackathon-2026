"""Identifiers that the public record/document readers can actually resolve."""
from collections import Counter

RECORD_KEYS = {'ledger': 'row_id', 'invoices': 'invoice_id',
               'payments': 'payment_id', 'fx': 'rate_id'}


def record_identifier(table, row):
    if table == 'fx' and not row.get('rate_id'):
        return ':'.join(row[key] for key in ('date', 'source_currency', 'target_currency'))
    return row.get(RECORD_KEYS[table])


def addressable_ids(public):
    """Foreign keys alone confer no evidence authority; ignore non-public tables.

    A record ID must resolve uniquely within its table, matching get_record.
    get_document exposes invoice/payment doc_id; duplicate doc IDs retain the
    existing reader's first-match behavior. This does not validate an episode.
    """
    ids = set()
    for table in RECORD_KEYS:
        rows = public['tables'].get(table, [])
        counts = Counter(record_identifier(table, row) for row in rows)
        ids.update(key for key, count in counts.items() if isinstance(key, str) and count == 1)
        if table in ('invoices', 'payments'):
            ids.update(row['doc_id'] for row in rows if isinstance(row.get('doc_id'), str))
    return ids
