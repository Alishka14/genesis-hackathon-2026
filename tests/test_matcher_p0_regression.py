"""P0 scoring regressions: semantics vs shape, addressability, stable tie-break.

All data are synthetic. These tests are independent of generator truth labels.
"""
from ledgergym.score import accessible_evidence_ids, evaluate, validate_submission


def _public():
    return {"tables": {
        "invoices": [{"invoice_id": "i1", "doc_id": "d1", "entity_id": "entity"},
                     {"invoice_id": "i2", "doc_id": "d2", "entity_id": "entity"}],
        "payments": [{"payment_id": "p1", "doc_id": "pdoc"}],
        "ledger": [{"row_id": "r1", "entity_id": "entity"}],
        "fx": [{"date": "2026-01-31", "source_currency": "USD",
                "target_currency": "KZT", "rate": "500"}],
    }}


def _case():
    finding = {"type": "duplicate_invoice", "affected_ids": ["i1", "i2"],
               "claimed_amount_minor": 100, "currency": "KZT",
               "evidence_ids": ["d1", "d2", "r1"], "explanation": "example"}
    issue = {"issue_id": "A", "type": "duplicate_invoice",
             "affected_ids": ["i1", "i2"], "expected_amount_minor": 100,
             "currency": "KZT", "allowed_evidence_sets": [["d1", "d2", "r1"]]}
    return finding, issue


def _score(finding, issue):
    return evaluate([issue], [finding], accessible_evidence_ids(_public()), 0)


def test_only_addressable_records_qualify_as_evidence():
    ids = accessible_evidence_ids(_public())
    assert {"i1", "i2", "d1", "d2", "r1", "p1", "pdoc",
            "2026-01-31:USD:KZT"} <= ids
    assert "entity" not in ids


def test_repeated_ids_are_set_semantics_and_not_malformed():
    finding, issue = _case()
    finding["affected_ids"] *= 2
    finding["evidence_ids"] *= 2
    assert validate_submission({"episode_id": "e", "findings": [finding]}, "e")
    assert (_score(finding, issue)["tp"], _score(finding, issue)["fp"]) == (1, 0)


def test_unknown_type_is_fp_not_invalid_submit():
    finding, issue = _case()
    finding["type"] = "unlisted"
    assert validate_submission({"episode_id": "e", "findings": [finding]}, "e")
    result = _score(finding, issue)
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)


def test_lowercase_currency_is_fp_not_invalid_submit():
    finding, issue = _case()
    finding["currency"] = "kzt"
    assert validate_submission({"episode_id": "e", "findings": [finding]}, "e")
    result = _score(finding, issue)
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)


def test_valid_extra_document_still_allows_full_evidence_set():
    finding, issue = _case()
    finding["evidence_ids"].append("pdoc")
    assert _score(finding, issue)["tp"] == 1


def test_unaddressable_entity_reference_invalidates_evidence():
    finding, issue = _case()
    finding["evidence_ids"].append("entity")
    result = _score(finding, issue)
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)


def test_lexicographic_ambiguity_tie_break(monkeypatch):
    finding, issue = _case()
    issues = [dict(issue, issue_id=k) for k in ("A", "B")]
    assignments = []
    import sys
    def trace(frame, event, arg):
        if event == "return" and frame.f_code is evaluate.__code__:
            assignments.append({issues[j]["issue_id"]: i for j, i in frame.f_locals["paired"].items()})
    old = sys.getprofile()
    try:
        sys.setprofile(trace)
        result = evaluate(issues, [finding, finding], accessible_evidence_ids(_public()), 0)
    finally:
        sys.setprofile(old)
    assert result["tp"] == 2
    assert assignments == [{"A": 0, "B": 1}]


def test_maximum_cardinality_not_order_greedy():
    finding, issue = _case()
    issues = [dict(issue, issue_id="A", allowed_evidence_sets=[["d1"], ["d2"]]),
              dict(issue, issue_id="B", allowed_evidence_sets=[["d1"]])]
    f1, f2 = dict(finding, evidence_ids=["d1"]), dict(finding, evidence_ids=["d2"])
    ids = accessible_evidence_ids(_public())
    assert evaluate(issues, [f1, f2], ids, 0)["tp"] == 2
    assert evaluate(issues, [f2, f1], ids, 0)["tp"] == 2


def test_evidence_raw_limit_applies_even_with_repeated_ids():
    finding, _ = _case()
    finding["evidence_ids"] *= 4
    assert not validate_submission({"episode_id": "e", "findings": [finding]}, "e")


def test_invalid_structure_is_still_rejected():
    finding, _ = _case()
    assert not validate_submission({"episode_id": "e", "findings": [dict(finding, claimed_amount_minor="100")]}, "e")
    assert not validate_submission({"episode_id": "e", "findings": [dict(finding, evidence_ids=[])]}, "e")
