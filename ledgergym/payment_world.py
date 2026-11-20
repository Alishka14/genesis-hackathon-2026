"""Deterministic payment-allocation example with explicit remittance evidence.

The optional remittance and allocation fields are provisional until the
competition's original public schema has been checked.
"""
import random
from ._checks import validate_invoice_total


def make_payment_episode(seed, mode="none"):
    if mode not in {"none", "missing", "partial"}:
        raise ValueError("unknown allocation scenario")
    rng = random.Random(seed)
    amount = 2 * rng.randint(5000, 49999)
    episode_id = f"episode-{rng.getrandbits(48):012x}"
    ids = [f"id-{rng.getrandbits(64):016x}" for _ in range(9)]
    entity, invoice_id, invoice_doc, payment_id, payment_doc, row1, row2, row3, row4 = ids
    stamp = "2026-01-10T12:00:00+00:00"
    invoice = {"doc_id": invoice_doc, "invoice_id": invoice_id, "entity_id": entity, "issued_at": stamp, "due_at": "2026-01-31T23:59:59+00:00", "currency": "KZT", "total_minor": 2 * amount, "line_items": [{"description": "Synthetic service", "amount_minor": 2 * amount}]}
    allocated = {"none": amount, "missing": 0, "partial": amount // 2}[mode]
    payment = {"doc_id": payment_doc, "payment_id": payment_id, "timestamp": stamp, "currency": "KZT", "amount_minor": amount, "remittance_invoice_id": invoice_id, "invoice_refs": [] if not allocated else [{"invoice_id": invoice_id, "amount_minor": allocated}]}
    def row(row_id, account, debit, credit, inv, pay):
        return {"row_id": row_id, "timestamp": stamp, "account": account, "debit_minor": debit, "credit_minor": credit, "currency": "KZT", "entity_id": entity, "invoice_id": inv, "payment_id": pay}
    rows = [row(row1, "expense", 2 * amount, 0, invoice_id, None), row(row2, "payable", 0, 2 * amount, invoice_id, None), row(row3, "payable", amount, 0, None, payment_id), row(row4, "bank", 0, amount, None, payment_id)]
    public = {"manifest": {"schema_version": "0.1", "episode_id": episode_id, "base_currency": "KZT", "period_start": "2026-01-01T00:00:00+00:00", "period_end": "2026-01-31T23:59:59+00:00", "timezone": "+00:00", "rounding": "ROUND_HALF_EVEN", "counts": {"invoices": 1, "ledger": 4, "payments": 1, "fx": 0}}, "policy": {"rounding": "ROUND_HALF_EVEN", "fx_date": "transaction_date", "cutoff_timezone": "+00:00", "allocation_rule": "allocate_full_payment_to_remittance_invoice"}, "tables": {"invoices": [invoice], "ledger": rows, "payments": [payment], "fx": []}}
    issues = [] if allocated == amount else [{"issue_id": f"private-{rng.getrandbits(64):016x}", "type": "payment_allocation", "affected_ids": [invoice_id, payment_id], "expected_amount_minor": amount - allocated, "currency": "KZT", "allowed_evidence_sets": [[invoice_doc, payment_doc, row3, row4]]}]
    truth = {"issues": issues}
    validate_payment_episode(public, truth)
    return public, truth


def validate_payment_episode(public, truth):
    """Derive the gap independently from the payment, remittance and ledger."""
    def reject(reason):
        raise ValueError(reason)
    try:
        tables = public["tables"]
        invoices, payments, ledger = tables["invoices"], tables["payments"], tables["ledger"]
        if len(invoices) != 1 or len(payments) != 1 or len(ledger) != 4 or tables["fx"]:
            reject("unsupported fixture shape")
        if public["policy"]["allocation_rule"] != "allocate_full_payment_to_remittance_invoice":
            reject("unsupported allocation policy")
        if any(public["manifest"]["counts"][name] != len(tables[name]) for name in tables):
            reject("manifest count mismatch")
        invoice, payment = invoices[0], payments[0]
        validate_invoice_total(invoice)
        ids = [invoice["doc_id"], invoice["invoice_id"], payment["doc_id"], payment["payment_id"], *[r["row_id"] for r in ledger]]
        if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
            reject("non-unique or invalid IDs")
        if invoice["currency"] != payment["currency"] or payment["remittance_invoice_id"] != invoice["invoice_id"]:
            reject("invalid remittance")
        amount, invoice_amount = payment["amount_minor"], invoice["total_minor"]
        if type(amount) is not int or type(invoice_amount) is not int or amount <= 0 or invoice_amount < amount:
            reject("invalid payment amount")
        allocations = payment["invoice_refs"]
        if not isinstance(allocations, list) or len(allocations) > 1:
            reject("invalid allocation list")
        allocated = 0
        for ref in allocations:
            if not isinstance(ref, dict) or set(ref) != {"invoice_id", "amount_minor"} or ref["invoice_id"] != invoice["invoice_id"] or type(ref["amount_minor"]) is not int or ref["amount_minor"] <= 0:
                reject("invalid allocation")
            allocated += ref["amount_minor"]
        if allocated > amount:
            reject("overallocated")
        for r in ledger:
            if r["currency"] != invoice["currency"] or r["entity_id"] != invoice["entity_id"]:
                reject("journal scope mismatch")
        invoice_rows = [r for r in ledger if r["invoice_id"] == invoice["invoice_id"] and r["payment_id"] is None]
        payment_rows = [r for r in ledger if r["invoice_id"] is None and r["payment_id"] == payment["payment_id"]]
        if len(invoice_rows) != 2 or len(payment_rows) != 2:
            reject("missing or incorrect journal references")
        signature = lambda rows: {(r["account"], r["debit_minor"], r["credit_minor"]) for r in rows}
        if signature(invoice_rows) != {("expense", invoice_amount, 0), ("payable", 0, invoice_amount)} or signature(payment_rows) != {("payable", amount, 0), ("bank", 0, amount)}:
            reject("unbalanced journals")
        gap = amount - allocated
        issues = truth["issues"]
        if len(issues) != int(gap > 0):
            reject("truth count does not match allocation")
        if gap:
            issue = issues[0]
            required = {invoice["doc_id"], payment["doc_id"], *[r["row_id"] for r in payment_rows]}
            if issue["type"] != "payment_allocation" or set(issue["affected_ids"]) != {invoice["invoice_id"], payment["payment_id"]} or issue["expected_amount_minor"] != gap or issue["currency"] != invoice["currency"] or not issue["allowed_evidence_sets"]:
                reject("truth does not match allocation")
            if any(not isinstance(s, list) or not required <= set(s) or not set(s) <= set(ids) for s in issue["allowed_evidence_sets"]):
                reject("missing or invalid evidence")
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("malformed episode") from exc
