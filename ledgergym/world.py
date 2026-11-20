"""Small deterministic audit fixture; not a full contest data generator."""
import random


def make_episode(seed, fault=True):
    """Create one explicit duplicate or an equal-amount valid control."""
    if not isinstance(fault, bool):
        raise ValueError("fault must be a bool")
    rng = random.Random(seed)
    amount = rng.randint(10000, 99999)
    episode_id = f"episode-{rng.getrandbits(48):012x}"
    ids = [f"id-{rng.getrandbits(64):016x}" for _ in range(11)]
    entity, inv1, inv2, doc1, doc2, row1, row2, row3, row4, service1, service2 = ids
    stamp = "2026-01-10T12:00:00+00:00"
    def invoice(invoice_id, doc_id, service_ref):
        return {"doc_id": doc_id, "invoice_id": invoice_id, "entity_id": entity, "issued_at": stamp, "due_at": "2026-01-31T23:59:59+00:00", "currency": "KZT", "total_minor": amount, "line_items": [{"description": "Synthetic service", "service_ref": service_ref, "amount_minor": amount}]}
    invoices = [invoice(inv1, doc1, service1), invoice(inv2, doc2, service1 if fault else service2)]
    rows = [{"row_id": row, "timestamp": stamp, "account": account, "debit_minor": amount if account == "expense" else 0, "credit_minor": amount if account == "payable" else 0, "currency": "KZT", "entity_id": entity, "invoice_id": invoice_id, "payment_id": None}
            for row, account, invoice_id in [(row1, "expense", inv1), (row2, "payable", inv1), (row3, "expense", inv2), (row4, "payable", inv2)]]
    public = {"manifest": {"schema_version": "0.1", "episode_id": episode_id, "base_currency": "KZT", "period_start": "2026-01-01T00:00:00+00:00", "period_end": "2026-01-31T23:59:59+00:00", "timezone": "+00:00", "rounding": "ROUND_HALF_EVEN", "counts": {"invoices": 2, "ledger": 4, "payments": 0, "fx": 0}}, "policy": {"rounding": "ROUND_HALF_EVEN", "fx_date": "transaction_date", "cutoff_timezone": "+00:00", "duplicate_rule": "one_invoice_per_service_ref"}, "tables": {"invoices": invoices, "ledger": rows, "payments": [], "fx": []}}
    issues = [] if not fault else [{"issue_id": f"private-{rng.getrandbits(64):016x}", "type": "duplicate_invoice", "affected_ids": [inv1, inv2], "expected_amount_minor": amount, "currency": "KZT", "allowed_evidence_sets": [[doc1, doc2, row1, row3]]}]
    truth = {"issues": issues}
    validate_episode(public, truth)
    return public, truth


def validate_episode(public, truth):
    """Preflight the supported fixture using public facts, not injected labels.

    This validator intentionally rejects other shapes until their rules exist.
    It does not certify the complete P0 generator or isolation.
    """
    def reject(message):
        raise ValueError(message)
    try:
        tables = public["tables"]
        invoices, rows = tables["invoices"], tables["ledger"]
        if len(invoices) != 2 or len(rows) != 4 or tables["payments"] or tables["fx"]:
            reject("unsupported fixture shape")
        if public["policy"]["duplicate_rule"] != "one_invoice_per_service_ref":
            reject("unsupported duplicate policy")
        if any(public["manifest"]["counts"][name] != len(tables[name]) for name in tables):
            reject("manifest counts differ")
        public_ids = [i["invoice_id"] for i in invoices] + [i["doc_id"] for i in invoices] + [r["row_id"] for r in rows]
        if any(not isinstance(x, str) or not x for x in public_ids) or len(public_ids) != len(set(public_ids)):
            reject("record IDs must be unique")
        invoice_ids = {i["invoice_id"] for i in invoices}
        if any(r["invoice_id"] not in invoice_ids for r in rows):
            reject("unknown invoice reference")
        for invoice in invoices:
            amount = invoice["total_minor"]
            items = invoice["line_items"]
            if type(amount) is not int or amount <= 0 or len(items) != 1 or items[0]["amount_minor"] != amount or not isinstance(items[0]["service_ref"], str) or not items[0]["service_ref"]:
                reject("invalid invoice")
            postings = [r for r in rows if r["invoice_id"] == invoice["invoice_id"]]
            if len(postings) != 2 or {r["account"] for r in postings} != {"expense", "payable"}:
                reject("missing invoice postings")
            if any(r["currency"] != invoice["currency"] or r["entity_id"] != invoice["entity_id"] for r in postings):
                reject("posting scope mismatch")
            expense = next(r for r in postings if r["account"] == "expense")
            payable = next(r for r in postings if r["account"] == "payable")
            if (expense["debit_minor"], expense["credit_minor"], payable["debit_minor"], payable["credit_minor"]) != (amount, 0, 0, amount):
                reject("unbalanced postings")
        first, second = invoices
        duplicate = (first["entity_id"], first["line_items"][0]["service_ref"]) == (second["entity_id"], second["line_items"][0]["service_ref"])
        issues = truth["issues"]
        if len(issues) != int(duplicate):
            reject("truth does not match public identity")
        if duplicate:
            issue = issues[0]
            if first["currency"] != second["currency"] or first["total_minor"] != second["total_minor"]:
                reject("unsupported duplicate amount")
            required = {i["doc_id"] for i in invoices} | {r["row_id"] for r in rows if r["account"] == "expense"}
            if (issue["type"] != "duplicate_invoice" or set(issue["affected_ids"]) != invoice_ids or issue["expected_amount_minor"] != second["total_minor"] or issue["currency"] != second["currency"] or not issue["allowed_evidence_sets"]):
                reject("truth differs from public facts")
            if any(not isinstance(s, list) or not required <= set(s) or not set(s) <= set(public_ids) for s in issue["allowed_evidence_sets"]):
                reject("evidence not public or incomplete")
    except (KeyError, TypeError, StopIteration, IndexError) as exc:
        raise ValueError("malformed episode") from exc
