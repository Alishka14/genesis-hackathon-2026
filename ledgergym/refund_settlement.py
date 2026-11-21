"""Conservative same-currency settlement extension: explicit vendor refunds.

This is a trusted, standalone P1 *fixture/validation* helper, not a change to
the official company policy or public episode schema. Refunds are repayments
of settled vendor transfers while the invoice remains payable. They must
reference both the original transfer and exact invoice allocations.

Supported: fully allocated positive transfers, split payments, later partial
refunds in the original currency. No guessing, no FX conversion, no negative
"payments", no credit-note semantics, no interleaved fresh transfers.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import re

from .payment_matching import allocate_payments


def _identifier(value):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
        raise ValueError("invalid identifier")
    return value


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if instant.utcoffset() is None:
        raise ValueError("timestamp offset required")
    return instant.astimezone(timezone.utc)


def _money(value):
    if type(value) is not int or value <= 0:
        raise ValueError("refund amount must be positive integer minor units")
    return value


def apply_refunds(invoices, payments, refunds):
    """Apply documented refunds to already settled same-currency allocations.

    Original input is unchanged. The refund list must be chronologically AFTER
    all positive transfers. Every claim must identify a unique original
    payment/invoice allocation, and cumulative refunds may not exceed it.
    The function rejects an invalid batch atomically, without silently
    selecting a winner by ID or input order.
    """
    if not isinstance(refunds, list):
        raise ValueError("refunds must be a list")
    payment_result = allocate_payments(invoices, payments)
    if any(row["status"] != "ALLOCATED" for row in payment_result["payments"].values()):
        raise ValueError("only fully allocated ordinary payments supported")
    invoice_by_id = {i["invoice_id"]: i for i in invoices}
    payment_by_id = {p["payment_id"]: p for p in payments}
    if len(invoice_by_id) != len(invoices) or len(payment_by_id) != len(payments):
        raise ValueError("duplicate original record IDs")
    last_payment = max((_instant(p["timestamp"]) for p in payments), default=None)

    # The explicitly applied money by (original payment, invoice). No refund
    # can point to an unrelated or merely similarly valued invoice.
    available = {
        (pid, a["invoice_id"]): a["amount_minor"]
        for pid, entry in payment_result["payments"].items()
        for a in entry["allocations"]
    }
    normalized = {}
    claimed = defaultdict(int)
    reserved_ids = set(invoice_by_id) | set(payment_by_id)
    for invoice in invoices:
        if "doc_id" in invoice:
            reserved_ids.add(invoice["doc_id"])
    for payment in payments:
        if "doc_id" in payment:
            reserved_ids.add(payment["doc_id"])

    for refund in refunds:
        if not isinstance(refund, dict) or set(refund) != {
            "refund_id", "kind", "original_payment_id", "entity_id",
            "currency", "timestamp", "amount_minor", "invoice_refs"
        }:
            raise ValueError("refund schema mismatch")
        rid = _identifier(refund["refund_id"])
        if rid in normalized or rid in reserved_ids:
            raise ValueError("duplicate refund ID")
        if refund["kind"] != "refund":
            raise ValueError("unsupported movement kind")
        original_id = _identifier(refund["original_payment_id"])
        if original_id not in payment_by_id:
            raise ValueError("unrecognized original payment")
        original = payment_by_id[original_id]
        entity = _identifier(refund["entity_id"])
        currency = refund["currency"]
        if not isinstance(currency, str) or not re.fullmatch("[A-Z]{3}", currency):
            raise ValueError("invalid refund currency")
        if entity != _identifier(original["entity_id"]) or currency != original["currency"]:
            raise ValueError("refund entity/currency mismatch")
        stamp = _instant(refund["timestamp"])
        if last_payment is not None and stamp <= last_payment:
            raise ValueError("refund must occur after ordinary transfers")
        amount = _money(refund["amount_minor"])
        refs = refund["invoice_refs"]
        if not isinstance(refs, list) or not refs:
            raise ValueError("explicit refund invoice references required")
        subtotal, seen, normalized_refs = 0, set(), []
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"invoice_id", "amount_minor"}:
                raise ValueError("invalid refund invoice reference")
            iid, applied = _identifier(ref["invoice_id"]), _money(ref["amount_minor"])
            if iid in seen:
                raise ValueError("repeated invoice in refund")
            seen.add(iid)
            if iid not in invoice_by_id or (original_id, iid) not in available:
                raise ValueError("refund invoice not part of original payment")
            invoice = invoice_by_id[iid]
            if invoice["entity_id"] != entity or invoice["currency"] != currency:
                raise ValueError("refund source invoice mismatch")
            subtotal += applied
            claimed[(original_id, iid)] += applied
            normalized_refs.append({"invoice_id": iid, "amount_minor": applied})
        if amount != subtotal:
            raise ValueError("refund amount does not equal referenced amounts")
        normalized[rid] = {
            "original_payment_id": original_id, "entity_id": entity,
            "currency": currency, "timestamp": refund["timestamp"],
            "amount_minor": amount,
            "invoice_refs": sorted(normalized_refs, key=lambda x: x["invoice_id"]),
            "status": "APPLIED",
        }

    if any(amount > available[key] for key, amount in claimed.items()):
        raise ValueError("cumulative refunds exceed original allocation")

    balances = deepcopy(payment_result["invoice_balances"])
    for (pid, iid), amount in claimed.items():
        current = balances[iid]
        current["paid_minor"] -= amount
        current["outstanding_minor"] += amount
        if not 0 <= current["paid_minor"] <= invoice_by_id[iid]["total_minor"]:
            raise ValueError("invalid invoice balance after refund")
    return {
        "payments": payment_result["payments"],
        "refunds": dict(sorted(normalized.items())),
        "invoice_balances": balances,
    }
