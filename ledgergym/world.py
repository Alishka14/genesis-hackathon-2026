"""Small deterministic teaching fixture; not yet the full contest generator."""
import random


def make_episode(seed, fault=True):
    rng = random.Random(seed)
    amount = rng.randint(10000, 99999)
    episode_id = f"episode-{rng.getrandbits(48):012x}"
    ids = [f"id-{rng.getrandbits(64):016x}" for _ in range(9)]
    entity, inv1, inv2, doc1, doc2, row1, row2, row3, row4 = ids
    stamp = "2026-01-10T12:00:00+00:00"
    invoice1 = {"doc_id": doc1, "invoice_id": inv1, "entity_id": entity, "issued_at": stamp, "due_at": "2026-01-31T23:59:59+00:00", "currency": "KZT", "total_minor": amount, "line_items": [{"description": "Synthetic service", "amount_minor": amount}]}
    invoice2 = dict(invoice1, doc_id=doc2, invoice_id=inv2)
    if not fault:
        invoice2 = dict(invoice2, total_minor=amount + 1, line_items=[{"description": "Other service", "amount_minor": amount + 1}])
    rows = [{"row_id": row1, "timestamp": stamp, "account": "expense", "debit_minor": amount, "credit_minor": 0, "currency": "KZT", "entity_id": entity, "invoice_id": inv1, "payment_id": None},
            {"row_id": row2, "timestamp": stamp, "account": "payable", "debit_minor": 0, "credit_minor": amount, "currency": "KZT", "entity_id": entity, "invoice_id": inv1, "payment_id": None},
            {"row_id": row3, "timestamp": stamp, "account": "expense", "debit_minor": invoice2["total_minor"], "credit_minor": 0, "currency": "KZT", "entity_id": entity, "invoice_id": inv2, "payment_id": None},
            {"row_id": row4, "timestamp": stamp, "account": "payable", "debit_minor": 0, "credit_minor": invoice2["total_minor"], "currency": "KZT", "entity_id": entity, "invoice_id": inv2, "payment_id": None}]
    public = {"manifest": {"schema_version": "0.1", "episode_id": episode_id, "base_currency": "KZT", "period_start": "2026-01-01T00:00:00+00:00", "period_end": "2026-01-31T23:59:59+00:00", "timezone": "+00:00", "rounding": "ROUND_HALF_EVEN", "counts": {"invoices": 2, "ledger": 4, "payments": 0, "fx": 0}}, "policy": {"rounding": "ROUND_HALF_EVEN", "fx_date": "transaction_date", "cutoff_timezone": "+00:00"}, "tables": {"invoices": [invoice1, invoice2], "ledger": rows, "payments": [], "fx": []}}
    issues = [] if not fault else [{"issue_id": f"private-{rng.getrandbits(64):016x}", "type": "duplicate_invoice", "affected_ids": [inv1, inv2], "expected_amount_minor": amount, "currency": "KZT", "allowed_evidence_sets": [[doc1, doc2, row1, row3]]}]
    return public, {"issues": issues}
