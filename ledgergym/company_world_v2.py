"""Clean, complete six-file company episodes with split transfers and refunds.

Versioned accounting extension. The v1 four-fault generator stays untouched.
This is the clean/hard-negative branch, so private truth is always empty;
an explicitly non-empty fault config is rejected, never silently ignored.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime

from .company_world import build_company
from .company_checks_v2 import validate_settlement_company


VERSION = "company-settlements-0.1"
MODEL = "accrual_company_v2"
SCHEMA = "0.4-company-settlements"


def build_settlement_company(seed: int, config: dict):
    if type(seed) is not int or not isinstance(config, dict):
        raise ValueError("seed must be integer and config object")
    if set(config) - {"postings", "documents"}:
        raise ValueError("settlement company supports clean episodes only; faults belong to v1")
    sizes = {"postings": config.get("postings", 400), "documents": config.get("documents", 80)}
    public, truth, base_provenance = build_company(seed, sizes)
    if truth["issues"]:
        raise ValueError("expected a clean source company")
    base_digest = hashlib.sha256(
        json.dumps(public, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    public = copy.deepcopy(public)
    tables = public["tables"]
    invoices = {row["invoice_id"]: row for row in tables["invoices"]}
    payments = tables["payments"]
    payment_rows = {}
    for row in tables["ledger"]:
        if row["payment_id"] is not None:
            payment_rows.setdefault(row["payment_id"], []).append(row)
    if any(len(payment_rows.get(p["payment_id"], [])) != 2 for p in payments):
        raise ValueError("source payment journal incomplete")

    # In the source company every invoice pair shares a real vendor, date,
    # currency and invoice amount, but has two DISTINCT service_ref values.
    eligible = []
    for payment in payments:
        target = invoices[payment["remittance_invoice_id"]]
        payment["entity_id"] = target["entity_id"]
        payment["kind"] = "payment"
        if target["currency"] != "KZT":
            continue
        alternatives = [
            other for other in invoices.values()
            if other["invoice_id"] != target["invoice_id"]
            and other["entity_id"] == target["entity_id"]
            and other["currency"] == target["currency"]
            and other["issued_at"] == target["issued_at"]
            and other["total_minor"] == target["total_minor"]
            and other["line_items"][0]["service_ref"] != target["line_items"][0]["service_ref"]
        ]
        if len(alternatives) == 1 and payment["amount_minor"] >= 2:
            eligible.append((payment, target, alternatives[0]))
    eligible.sort(key=lambda group: group[0]["payment_id"])
    if len(eligible) < 3:
        raise ValueError("not enough independently payable KZT invoice pairs")
    origin, origin_invoice, _ = eligible[0]
    replaced, _, _ = eligible[1]
    split, primary, secondary = eligible[2]
    assert len({origin["payment_id"], replaced["payment_id"], split["payment_id"]}) == 3

    split_amount = split["amount_minor"]
    first_share = split_amount // 2
    split["invoice_refs"] = [
        {"invoice_id": primary["invoice_id"], "amount_minor": first_share},
        {"invoice_id": secondary["invoice_id"], "amount_minor": split_amount - first_share},
    ]
    # The vendor's documented remittance schedule is the independent basis
    # for checking whether invoice_refs were actually applied correctly.
    # It is present in BOTH clean and faulty v2 episodes and is public evidence.
    split["allocation_basis"] = copy.deepcopy(split["invoice_refs"])
    split["remittance_invoice_id"] = None
    for row in payment_rows[split["payment_id"]]:
        # A vendor-level AP control debit covers multiple invoice references.
        # The document holds the invoice-level allocation; no extra journal row.
        row["invoice_id"] = None

    refund_amount = max(1, origin["amount_minor"] // 3)
    refund_timestamp = "2026-02-27T12:00:00+05:00"
    latest_transfer = max(datetime.fromisoformat(p["timestamp"]) for p in payments)
    if datetime.fromisoformat(refund_timestamp) <= latest_transfer:
        raise ValueError("refund timestamp not after ordinary transfers")
    refund_id = replaced["payment_id"]
    replaced.update({
        "kind": "refund",
        "original_payment_id": origin["payment_id"],
        "entity_id": origin_invoice["entity_id"],
        "timestamp": refund_timestamp,
        "currency": "KZT",
        "amount_minor": refund_amount,
        "remittance_invoice_id": None,
        "invoice_refs": [{"invoice_id": origin_invoice["invoice_id"], "amount_minor": refund_amount}],
    })
    for row in payment_rows[refund_id]:
        row["timestamp"] = refund_timestamp
        row["reporting_period"] = "2026-02"
        row["entity_id"] = origin_invoice["entity_id"]
        row["invoice_id"] = None
        row["rate_id"] = None
        # Inverse of a positive vendor settlement:
        # cash/bank debit, accounts payable credit.
        if row["account"] == "payable":
            row["debit_minor"] = 0
            row["credit_minor"] = refund_amount
        elif row["account"] == "bank":
            row["debit_minor"] = refund_amount
            row["credit_minor"] = 0
        else:
            raise ValueError("unsupported source bank or payable account")

    public["manifest"]["schema_version"] = SCHEMA
    public["policy"].update({
        "accounting_model": MODEL,
        "allocation_rule": "explicit_same_currency_invoice_refs",
        "payment_journal_basis": "vendor_ap_control",
        "refund_rule": "linked_after_all_positive_payments",
        "refund_currency": "KZT",
        "refund_invoice_effect": "restore_outstanding",
    })
    # Private provenance is not sent to a policy or embedded in a public file.
    provenance = {
        "seed": seed,
        "generator_version": VERSION,
        "base_generator_version": base_provenance["generator_version"],
        "base_company_sha256": base_digest,
        "config": sizes,
        "clean_preflight": "passed",
        "interventions": [],
        "compound_groups": [],
        "clean_cases": [
            {"kind": "split_payment", "payment_id": split["payment_id"],
             "invoice_ids": [primary["invoice_id"], secondary["invoice_id"]]},
            {"kind": "supplier_refund", "payment_id": refund_id,
             "original_payment_id": origin["payment_id"],
             "invoice_id": origin_invoice["invoice_id"]},
        ],
    }
    empty_truth = {"issues": []}
    validate_settlement_company(public, empty_truth)
    return public, empty_truth, provenance
