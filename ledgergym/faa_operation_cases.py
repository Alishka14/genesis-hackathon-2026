"""Evaluator-only, per-payment FAA opportunities in validated synthetic companies.

These labels are a research instrument, not agent observations. A trusted
caller must validate (public, truth) using the model-specific validator first.
Only payment operations not implicated by *any* official issue are labelled.
"""
from __future__ import annotations

from .research_diagnostics import STANDARD_VALID, SUSPICIOUS_BUT_VALID
from .score import accessible_evidence_ids


def _refs(payment):
    rows = payment.get("invoice_refs")
    if not isinstance(rows, list) or not rows:
        return None
    values = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        invoice_id, amount = row.get("invoice_id"), row.get("amount_minor")
        if (not isinstance(invoice_id, str) or not invoice_id
                or type(amount) is not int or amount <= 0
                or invoice_id in values):
            return None
        values[invoice_id] = amount
    return values


def verified_payment_operations(public, truth):
    """Build only unambiguous case labels for normal and suspicious-valid payments.

    No issue-affected ID may belong to a labelled case. This excludes e.g. a
    legitimately paid invoice with a known duplicate or period violation:
    whether the *payment* is clean cannot justify treating the whole linked
    transaction as fault-free. V2 split/refund classes are hard negatives only
    if their explicit public policy, references and source links are coherent.

    A valid company may contain other clean invoice operations. They are not
    counted: the denominator is *verified eligible payment operations*, not
    all accounting postings or entire companies.
    """
    if (not isinstance(public, dict) or not isinstance(truth, dict)
            or not isinstance(public.get("tables"), dict)
            or not isinstance(public.get("policy"), dict)
            or not isinstance(truth.get("issues"), list)):
        raise ValueError("expected validated financial episode and truth")

    model = public["policy"].get("accounting_model")
    if model not in {"accrual_company_v1", "accrual_company_v2"}:
        return {}

    payments = public["tables"].get("payments")
    invoices = public["tables"].get("invoices")
    if not isinstance(payments, list) or not isinstance(invoices, list):
        raise ValueError("missing public operations")

    payment_ids = [p.get("payment_id") for p in payments
                   if isinstance(p, dict)]
    invoice_ids = [i.get("invoice_id") for i in invoices
                   if isinstance(i, dict)]
    if (len(payment_ids) != len(payments) or len(invoice_ids) != len(invoices)
            or any(not isinstance(i, str) or not i for i in payment_ids + invoice_ids)
            or len(set(payment_ids)) != len(payment_ids)
            or len(set(invoice_ids)) != len(invoice_ids)):
        raise ValueError("duplicate or malformed operation ID")

    known_payments, known_invoices = set(payment_ids), set(invoice_ids)
    public_ids = accessible_evidence_ids(public)
    implicated = set()
    for issue in truth["issues"]:
        if not isinstance(issue, dict) or not isinstance(issue.get("affected_ids"), list):
            raise ValueError("invalid truth affected IDs")
        ids = issue["affected_ids"]
        if not all(isinstance(i, str) and i for i in ids):
            raise ValueError("invalid truth affected IDs")
        implicated.update(ids)

    cases = {}
    for payment in sorted(payments, key=lambda item: item["payment_id"]):
        pid = payment["payment_id"]
        refs = _refs(payment)
        if refs is None:
            continue
        kind = STANDARD_VALID
        case_invoice_ids = None

        if model == "accrual_company_v1":
            target = payment.get("remittance_invoice_id")
            if (target in known_invoices and refs == {target: payment.get("amount_minor")}):
                case_invoice_ids = {target}

        elif payment.get("kind") == "payment":
            basis = payment.get("allocation_basis")
            if basis is not None:
                intended = _refs({"invoice_refs": basis})
                if (intended is not None and len(intended) == 2
                        and intended == refs and set(refs) <= known_invoices
                        and payment.get("remittance_invoice_id") is None):
                    case_invoice_ids = set(refs)
                    kind = SUSPICIOUS_BUT_VALID
            else:
                target = payment.get("remittance_invoice_id")
                if (target in known_invoices and refs == {target: payment.get("amount_minor")}):
                    case_invoice_ids = {target}

        elif payment.get("kind") == "refund":
            origin = payment.get("original_payment_id")
            if (isinstance(origin, str) and origin in known_payments
                    and origin != pid and len(refs) == 1
                    and set(refs) <= known_invoices
                    and sum(refs.values()) == payment.get("amount_minor")
                    and payment.get("remittance_invoice_id") is None):
                case_invoice_ids = set(refs)
                kind = SUSPICIOUS_BUT_VALID

        if case_invoice_ids is None:
            continue
        involved = {pid, *case_invoice_ids}
        if involved & implicated or not involved <= public_ids:
            continue
        # Private classifier identifiers; no IDs or individual labels exported
        # into aggregate research_summary.json.
        cases[pid] = {"kind": kind, "affected_ids": sorted(involved)}
    return cases
