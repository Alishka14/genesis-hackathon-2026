"""Strict, evaluator-only EQT annotations from *public* financial facts.

These comparisons supplement research taxonomy and never change official score.
Do not expose annotations to the closed-mode agent. No private truth is read.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import re

from .research_diagnostics import EQT, evidence_taxonomy


def _unique_index(rows, key):
    index = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid public record")
        value = row.get(key)
        if not isinstance(value, str) or not value or value in index:
            raise ValueError("duplicate or missing public record ID")
        index[value] = row
    return index


def _cutoff_zone(policy):
    raw = policy.get("cutoff_timezone")
    if not isinstance(raw, str):
        raise ValueError("missing cutoff timezone")
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", raw)
    if not match or int(match[2]) > 23 or int(match[3]) > 59:
        raise ValueError("invalid cutoff timezone")
    minutes = int(match[2]) * 60 + int(match[3])
    sign = 1 if match[1] == "+" else -1
    return timezone(timedelta(minutes=sign * minutes))


def _local_date(value, zone):
    if not isinstance(value, str):
        raise ValueError("missing payment timestamp")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid payment timestamp") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("payment timestamp requires explicit offset")
    return moment.astimezone(zone).date().isoformat()


def infer_public_evidence_labels(public, finding):
    """Find only two directly provable inconsistencies in v1 public records.

    A label is added only if BOTH the payment source document and the journal
    row are cited as evidence. On a USD payment, a referenced posting whose
    applied FX rate has a different local date is temporally invalid.
    A cited posting with invoice_id different from the payment document's
    remittance_invoice_id contradicts that document.

    Unsupported models/policies are not guessed at. Rate VALUE discrepancies,
    invoice allocations and unannotated contradiction cases remain unknown.
    """
    empty = {"temporally_invalid_ids": set(),
             "contradictory_ids": set(), "verified_comparisons": 0,
             "supported_policy": False}
    if not isinstance(public, dict) or not isinstance(finding, dict):
        raise TypeError("expected public episode and finding mappings")
    policy = public.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("missing public policy")
    if (policy.get("accounting_model") != "accrual_company_v1"
            or policy.get("fx_date") != "local_transaction_date"):
        return empty
    tables = public.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("missing public records")
    try:
        payments = _unique_index(tables["payments"], "payment_id")
        rows = _unique_index(tables["ledger"], "row_id")
        rates = _unique_index(tables["fx"], "rate_id")
    except (KeyError, TypeError) as exc:
        raise ValueError("incomplete public records") from exc
    evidence = finding.get("evidence_ids")
    if (not isinstance(evidence, list)
            or not all(isinstance(item, str) for item in evidence)):
        raise ValueError("invalid finding evidence")
    cited = set(evidence)
    zone = _cutoff_zone(policy)
    temporal, contradictory = set(), set()
    compared = 0
    for row_id in cited & rows.keys():
        row = rows[row_id]
        payment_id = row.get("payment_id")
        payment = payments.get(payment_id) if isinstance(payment_id, str) else None
        if payment is None or payment.get("doc_id") not in cited:
            continue
        compared += 1
        if (isinstance(row.get("invoice_id"), str)
                and isinstance(payment.get("remittance_invoice_id"), str)
                and row["invoice_id"] != payment["remittance_invoice_id"]):
            contradictory.add(row_id)
        if payment.get("currency") == "USD":
            used_rate = rates.get(row.get("rate_id"))
            if used_rate is not None:
                expected_date = _local_date(payment.get("timestamp"), zone)
                if used_rate.get("date") != expected_date:
                    temporal.add(row_id)
    return {"temporally_invalid_ids": temporal,
            "contradictory_ids": contradictory,
            "verified_comparisons": compared, "supported_policy": True}


def evidence_taxonomy_from_public(issues, findings, public_ids, public):
    """Apply proven v1 policy rules on each finding; avoid global false labels.

    An uncited invalid row cannot taint another finding. Original
    evidence_taxonomy behavior remains available for explicit annotations.
    """
    items = []
    compared = 0
    supported = False
    for finding in findings:
        flags = infer_public_evidence_labels(public, finding)
        row = evidence_taxonomy(
            issues, [finding], public_ids,
            temporally_invalid_ids=flags["temporally_invalid_ids"],
            contradictory_ids=flags["contradictory_ids"],
        )
        items.append(row["items"][0])
        compared += flags["verified_comparisons"]
        supported = supported or flags["supported_policy"]
    counts = Counter(tag for tags in items for tag in tags)
    return {
        "method": "evaluator_only_eqt_v1",
        "items": items,
        "counts": {tag: counts.get(tag, 0) for tag in EQT},
        "official_score_modified": False,
        "explicit_temporal_validation_only": False,
        "verified_public_policy_only": True,
        "public_policy_supported": supported,
        "verified_public_record_comparisons": compared,
    }
