"""Public-evidence v2 fault detection and clean-vs-fault causal pairing.

The detector reads public documents and derives candidate findings without
the private fault configuration or truth. After repairing *only* recognized
business discrepancies on a deep copy it runs the independent v2 clean audit.
Unrecognized structural/financial damage must fail instead of being labeled.
"""
from __future__ import annotations

import copy
import random
from collections import defaultdict

from .company_checks_v2 import validate_settlement_company
from .company_world_v2 import build_settlement_company
from .score import accessible_evidence_ids

FAULT_TYPES = ("duplicate_invoice", "payment_allocation", "duplicate_allocation")


def _signature(item):
    return (item["type"], tuple(sorted(item["affected_ids"])),
            item["claimed_amount_minor"], item["currency"])


def inspect_settlement_faults(public):
    """Return minimally evidenced findings inferred strictly from public data.

    This is a controlled synthetic v2 policy, not a general fraud detector.
    The public remittance allocation_basis is a vendor's intended split; the
    applied invoice_refs are the separate observed settlement allocations.
    """
    if public["policy"].get("accounting_model") != "accrual_company_v2":
        raise ValueError("unsupported financial model")
    cleaned = copy.deepcopy(public)
    invoices = {i["invoice_id"]: i for i in public["tables"]["invoices"]}
    repaired_invoices = {i["invoice_id"]: i for i in cleaned["tables"]["invoices"]}
    payment_rows = defaultdict(list)
    payable_rows = defaultdict(list)
    for row in public["tables"]["ledger"]:
        if row["payment_id"] is not None:
            payment_rows[row["payment_id"]].append(row)
        elif row["invoice_id"] is not None and row["account"] == "payable":
            payable_rows[row["invoice_id"]].append(row)

    found = []
    # A) Duplicate economic obligation: same vendor and documented service
    # basis with the same face amount/currency. Each invoice has a payable.
    obligations = defaultdict(list)
    for invoice in public["tables"]["invoices"]:
        services = {line["service_ref"] for line in invoice["line_items"]}
        if len(services) != 1:
            raise ValueError("unsupported mixed service reference")
        obligations[(invoice["entity_id"], next(iter(services)))].append(invoice)
    for group in obligations.values():
        if len(group) == 1:
            continue
        if len(group) != 2:
            raise ValueError("unsupported duplicate cardinality")
        first, second = sorted(group, key=lambda row: row["invoice_id"])
        if (first["currency"], first["total_minor"]) != (second["currency"], second["total_minor"]):
            raise ValueError("ambiguous duplicate obligation")
        if len(payable_rows[first["invoice_id"]]) != 1 or len(payable_rows[second["invoice_id"]]) != 1:
            raise ValueError("missing duplicate payable evidence")
        evidence = [
            first["doc_id"], second["doc_id"],
            payable_rows[first["invoice_id"]][0]["row_id"],
            payable_rows[second["invoice_id"]][0]["row_id"],
        ]
        found.append({
            "type": "duplicate_invoice",
            "affected_ids": sorted([first["invoice_id"], second["invoice_id"]]),
            "claimed_amount_minor": first["total_minor"],
            "currency": first["currency"],
            "evidence_ids": sorted(evidence), "explanation": "Duplicate vendor service obligation",
        })
        # This marker is used ONLY on the private in-memory verification copy.
        # No repaired field, guessed ID or issue annotation is ever serialized.
        repaired = repaired_invoices[second["invoice_id"]]
        distinct = "v2-audit-restored-" + second["invoice_id"]
        for line in repaired["line_items"]:
            line["service_ref"] = distinct

    # B) A public remittance schedule describes exactly which invoices the
    # vendor intended to settle. A partial split misallocation is the delta
    # between that schedule and the actual applied invoice references.
    repaired_payments = {p["payment_id"]: p for p in cleaned["tables"]["payments"]}
    for payment in public["tables"]["payments"]:
        basis = payment.get("allocation_basis")
        if basis is None:
            continue
        if payment.get("kind") != "payment" or payment["currency"] != "KZT" or len(basis) != 2:
            raise ValueError("unsupported remittance allocation basis")
        expected = {}
        actual = {}
        for ref in basis:
            iid, amount = ref["invoice_id"], ref["amount_minor"]
            if iid in expected or type(amount) is not int or amount <= 0 or iid not in invoices:
                raise ValueError("invalid remittance schedule")
            expected[iid] = amount
        for ref in payment["invoice_refs"]:
            iid, amount = ref["invoice_id"], ref["amount_minor"]
            if iid in actual or type(amount) is not int or amount <= 0:
                raise ValueError("invalid applied allocation")
            actual[iid] = amount
        if sum(expected.values()) != payment["amount_minor"] or set(expected) != set(actual):
            raise ValueError("invalid remittance reference identities")
        gaps = {iid: amount - actual[iid] for iid, amount in expected.items() if amount != actual[iid]}
        if not gaps:
            continue
        if len(gaps) != 1 or next(iter(gaps.values())) <= 0:
            raise ValueError("unsupported multi-invoice allocation corruption")
        affected_invoice = next(iter(gaps))
        if len(payment_rows[payment["payment_id"]]) != 2:
            raise ValueError("missing split payment journal")
        payable = [r for r in payment_rows[payment["payment_id"]] if r["account"] == "payable"]
        if len(payable) != 1:
            raise ValueError("missing split payment payable")
        found.append({
            "type": "payment_allocation",
            "affected_ids": sorted([payment["payment_id"], affected_invoice]),
            "claimed_amount_minor": gaps[affected_invoice], "currency": "KZT",
            "evidence_ids": sorted([
                payment["doc_id"], payable[0]["row_id"],
                *[invoices[iid]["doc_id"] for iid in expected],
            ]),
            "explanation": "Applied invoice split is short of the documented remittance schedule",
        })
        repaired_payments[payment["payment_id"]]["invoice_refs"] = copy.deepcopy(basis)

    # This independent validator recomputes ledger and cash invariants from
    # public values after only the two recognized errors have been repaired.
    # It rejects all other inconsistent financial histories.
    validate_settlement_company(cleaned, {"issues": []})
    ids = accessible_evidence_ids(public)
    if any(not set(item["evidence_ids"]) <= ids for item in found):
        raise ValueError("fault evidence is not publicly retrievable")
    return sorted(found, key=lambda f: _signature(f))


def validate_settlement_episode(public, truth):
    """Validate public v2 accounting and a private truth that exactly matches it."""
    if not isinstance(truth, dict) or set(truth) != {"issues"} or not isinstance(truth["issues"], list):
        raise ValueError("invalid private truth")
    derived = inspect_settlement_faults(public)
    expected = truth["issues"]
    if len(derived) != len(expected):
        raise ValueError("truth disagrees with public accounting evidence")
    remaining = {_signature(item): item for item in derived}
    ids = accessible_evidence_ids(public)
    used_issue_ids = set()
    for issue in expected:
        if not isinstance(issue, dict) or set(issue) != {
            "issue_id", "type", "affected_ids", "expected_amount_minor",
            "currency", "allowed_evidence_sets"
        }:
            raise ValueError("malformed issue")
        issue_id = issue["issue_id"]
        if not isinstance(issue_id, str) or issue_id in used_issue_ids:
            raise ValueError("repeated or invalid issue ID")
        used_issue_ids.add(issue_id)
        key = (issue["type"], tuple(sorted(issue["affected_ids"])),
               issue["expected_amount_minor"], issue["currency"])
        matched = remaining.pop(key, None)
        if matched is None:
            raise ValueError("truth issue does not match public financial evidence")
        sets = issue["allowed_evidence_sets"]
        if not isinstance(sets, list) or not sets or not any(
            isinstance(group, list) and 0 < len(group) <= 10
            and len(group) == len(set(group))
            and set(matched["evidence_ids"]) <= set(group) <= ids
            for group in sets
        ):
            raise ValueError("private evidence is not complete and accessible")
    if remaining:
        raise ValueError("unmatched publicly observable financial error")
    return {"issues": derived, "issue_count": len(derived)}


def build_settlement_fault_episode(seed, config):
    """Create a v2 company with exactly one or two controlled semantic faults.

    Same seed/config dimensions yield byte-identical public clean and faulty
    records except for the specifically altered business facts. Both models
    expose the same policy, schema version, identifiers and base episode ID.
    """
    if type(seed) is not int or type(config) is not dict:
        raise ValueError("invalid paired episode seed/config")
    if set(config) != {"postings", "documents", "fault"} or config["fault"] not in FAULT_TYPES:
        raise ValueError("supported fault is required; no silent coercion")
    mode = config["fault"]
    size = {"postings": config["postings"], "documents": config["documents"]}
    public, _, provenance = build_settlement_company(seed, size)
    payments = public["tables"]["payments"]
    invoices = {row["invoice_id"]: row for row in public["tables"]["invoices"]}
    split = next(p for p in payments if p["kind"] == "payment"
                 and len(p["invoice_refs"]) == 2 and "allocation_basis" in p)
    if len(split["allocation_basis"]) != 2:
        raise ValueError("expected documented two-invoice split")
    first = invoices[split["allocation_basis"][0]["invoice_id"]]
    second = invoices[split["allocation_basis"][1]["invoice_id"]]
    changes = []

    def change(table, record, field, value, identity_key):
        previous = copy.deepcopy(record[field])
        if previous == value:
            raise ValueError("inert intervention")
        changes.append({"table": table, "id": record[identity_key],
                        "field": field, "before": previous, "after": copy.deepcopy(value)})
        record[field] = copy.deepcopy(value)

    if mode in ("duplicate_invoice", "duplicate_allocation"):
        for line in second["line_items"]:
            change("invoices.line_items", line, "service_ref",
                   first["line_items"][0]["service_ref"], "line_id")

    if mode in ("payment_allocation", "duplicate_allocation"):
        applied = copy.deepcopy(split["invoice_refs"])
        target_index = max(range(len(applied)), key=lambda idx: applied[idx]["amount_minor"])
        if applied[target_index]["amount_minor"] < 2:
            raise ValueError("insufficient amount for partial allocation")
        applied[target_index]["amount_minor"] -= 1
        change("payments", split, "invoice_refs", applied, "payment_id")

    inferred = inspect_settlement_faults(public)
    wanted = {
        "duplicate_invoice": {"duplicate_invoice"},
        "payment_allocation": {"payment_allocation"},
        "duplicate_allocation": {"duplicate_invoice", "payment_allocation"},
    }[mode]
    if {item["type"] for item in inferred} != wanted or len(inferred) != len(wanted):
        raise ValueError("injected faults are not uniquely resolvable")
    private_rng = random.Random(f"company-settlements-v2-private:{seed}:{mode}")
    issues = []
    for item in inferred:
        issues.append({
            "issue_id": f"private-{private_rng.getrandbits(128):032x}",
            "type": item["type"],
            "affected_ids": item["affected_ids"],
            "expected_amount_minor": item["claimed_amount_minor"],
            "currency": item["currency"],
            "allowed_evidence_sets": [item["evidence_ids"]],
        })
    truth = {"issues": issues}
    provenance = copy.deepcopy(provenance)
    provenance["interventions"] = changes
    provenance["fault_mode"] = mode
    provenance["compound_groups"] = ([{"kind": "duplicate_allocation",
                                      "issue_ids": [i["issue_id"] for i in issues],
                                      "payment_id": split["payment_id"]}]
                                     if mode == "duplicate_allocation" else [])
    validate_settlement_episode(public, truth)
    return public, truth, provenance
