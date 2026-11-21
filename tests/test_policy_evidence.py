"""P1 EQT: public-policy temporal/contradiction evidence without score changes."""
import copy

import pytest

from ledgergym.policy_evidence import (
    evidence_taxonomy_from_public,
    infer_public_evidence_labels,
)
from ledgergym.score import evaluate


def _public():
    return {
        "policy": {
            "accounting_model": "accrual_company_v1",
            "fx_date": "local_transaction_date",
            "cutoff_timezone": "+05:00",
        },
        "tables": {
            "payments": [{
                "payment_id": "pay-1", "doc_id": "payment-doc",
                "timestamp": "2026-11-21T00:30:00+05:00",
                "currency": "USD", "remittance_invoice_id": "inv-1",
            }],
            "ledger": [{
                "row_id": "journal-1", "payment_id": "pay-1",
                "invoice_id": "inv-1", "rate_id": "fx-20",
            }],
            "fx": [
                {"rate_id": "fx-20", "date": "2026-11-20", "rate": "510"},
                {"rate_id": "fx-21", "date": "2026-11-21", "rate": "515"},
            ],
        },
    }


def _finding():
    return {
        "type": "fx_rate_or_date", "affected_ids": ["pay-1", "journal-1"],
        "claimed_amount_minor": 5, "currency": "KZT",
        "evidence_ids": ["payment-doc", "journal-1", "fx-21"],
        "explanation": "",
    }


def _issue():
    finding = _finding()
    return {
        "issue_id": "private-issue", "type": finding["type"],
        "affected_ids": finding["affected_ids"],
        "expected_amount_minor": finding["claimed_amount_minor"],
        "currency": finding["currency"],
        "allowed_evidence_sets": [finding["evidence_ids"]],
    }


def test_temporal_annotation_from_mismatched_applied_fx_date():
    public = _public()
    finding = _finding()
    flags = infer_public_evidence_labels(public, finding)
    assert flags["supported_policy"] is True
    assert flags["verified_comparisons"] == 1
    assert flags["temporally_invalid_ids"] == {"journal-1"}
    assert flags["contradictory_ids"] == set()
    before = evaluate([_issue()], [finding], set(finding["evidence_ids"] + finding["affected_ids"]), 3)
    eqt = evidence_taxonomy_from_public(
        [_issue()], [finding],
        set(finding["evidence_ids"] + finding["affected_ids"]), public)
    assert eqt["items"] == [["SUFFICIENT", "TEMPORALLY_INVALID"]]
    assert eqt["counts"]["TEMPORALLY_INVALID"] == 1
    assert eqt["official_score_modified"] is False
    assert evaluate([_issue()], [finding], set(finding["evidence_ids"] + finding["affected_ids"]), 3) == before


def test_utc_offset_conversion_and_valid_rate_are_not_false_positive():
    public = _public()
    public["tables"]["payments"][0]["timestamp"] = "2026-11-20T19:30:00+00:00"
    public["tables"]["ledger"][0]["rate_id"] = "fx-21"
    flags = infer_public_evidence_labels(public, _finding())
    assert flags["verified_comparisons"] == 1
    assert flags["temporally_invalid_ids"] == set()
    assert flags["contradictory_ids"] == set()


def test_contradiction_requires_cited_payment_document_and_journal_row():
    public = _public()
    public["tables"]["ledger"][0]["invoice_id"] = "inv-other"
    public["tables"]["ledger"][0]["rate_id"] = "fx-21"
    flags = infer_public_evidence_labels(public, _finding())
    assert flags["contradictory_ids"] == {"journal-1"}
    report = evidence_taxonomy_from_public([], [_finding()], set(_finding()["evidence_ids"] + ["pay-1", "journal-1"]), public)
    assert report["items"] == [["CONTRADICTORY_EVIDENCE"]]
    alone = copy.deepcopy(_finding())
    alone["evidence_ids"].remove("payment-doc")
    flags = infer_public_evidence_labels(public, alone)
    assert flags["contradictory_ids"] == set()
    assert flags["temporally_invalid_ids"] == set()


def test_unsupported_policy_never_guesses_tags():
    public = _public()
    public["policy"]["accounting_model"] = "accrual_company_v2"
    flags = infer_public_evidence_labels(public, _finding())
    assert flags["supported_policy"] is False
    assert flags["verified_comparisons"] == 0
    assert flags["contradictory_ids"] == flags["temporally_invalid_ids"] == set()
    finding = _finding()
    # EQT checks affected IDs and cited evidence independently from whether
    # the v1-only financial policy is supported. Both must be public here.
    public_ids = set(finding["evidence_ids"] + finding["affected_ids"])
    result = evidence_taxonomy_from_public([], [finding], public_ids, public)
    assert result["public_policy_supported"] is False
    assert result["items"] == [["UNDETERMINED"]]
    # An unsupported financial model must not suppress a genuinely
    # fabricated evidence/affected ID.
    fabricated = copy.deepcopy(finding)
    fabricated["evidence_ids"].append("nonpublic-doc")
    report = evidence_taxonomy_from_public([], [fabricated], public_ids, public)
    assert report["public_policy_supported"] is False
    assert report["items"] == [["FABRICATED_ID"]]


def test_wrong_time_or_timezone_fails_closed():
    public = _public()
    public["policy"]["cutoff_timezone"] = "local"
    with pytest.raises(ValueError, match="timezone"):
        infer_public_evidence_labels(public, _finding())
    public = _public()
    public["tables"]["payments"][0]["timestamp"] = "2026-11-21T00:30:00"
    with pytest.raises(ValueError, match="explicit offset"):
        infer_public_evidence_labels(public, _finding())


def test_ambiguous_duplicate_ids_fail_closed():
    public = _public()
    public["tables"]["ledger"].append(dict(public["tables"]["ledger"][0]))
    with pytest.raises(ValueError, match="duplicate or missing"):
        infer_public_evidence_labels(public, _finding())
