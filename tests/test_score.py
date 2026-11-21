from ledgergym.score import evaluate


def test_clean_and_false_accusation():
    assert evaluate([], [], set(), 0)["f1"] == 1
    finding = {"type": "duplicate_invoice", "affected_ids": ["i1"], "claimed_amount_minor": 100, "currency": "KZT", "evidence_ids": ["d1"], "explanation": "x"}
    result = evaluate([], [finding], {"i1", "d1"}, 0)
    assert (result["fp"], result["f1"], result["reward"]) == (1, 0, -1)


def test_matching_duplicate_and_missing_evidence():
    issue = {"issue_id": "private", "type": "duplicate_invoice", "affected_ids": ["i1", "i2"], "expected_amount_minor": 100, "currency": "KZT", "allowed_evidence_sets": [["d1", "d2"]]}
    finding = {"type": "duplicate_invoice", "affected_ids": ["i2", "i1"], "claimed_amount_minor": 100, "currency": "KZT", "evidence_ids": ["d2", "d1"], "explanation": "x"}
    result = evaluate([issue], [finding, finding], {"i1", "i2", "d1", "d2"}, 10)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 0)
    assert abs(result["reward"] - (2 * (2 / 3) - 1 - .02)) < 1e-10
    incomplete = dict(finding, evidence_ids=["d1"])
    assert evaluate([issue], [incomplete], {"i1", "i2", "d1", "d2"}, 0)["tp"] == 0


def test_maximum_matching_not_greedy_and_order_independent():
    common = {"type": "duplicate_invoice", "affected_ids": ["i1"], "expected_amount_minor": 100, "currency": "KZT"}
    issues = [dict(common, issue_id="x", allowed_evidence_sets=[["d1"], ["d2"]]), dict(common, issue_id="y", allowed_evidence_sets=[["d1"]])]
    f1 = {"type": "duplicate_invoice", "affected_ids": ["i1"], "claimed_amount_minor": 100, "currency": "KZT", "evidence_ids": ["d1"], "explanation": ""}
    f2 = dict(f1, evidence_ids=["d2"])
    for seq in ([f1, f2], [f2, f1]):
        assert evaluate(issues, seq, {"i1", "d1", "d2"}, 0)["tp"] == 2


def test_unknown_evidence_and_wrong_fields_do_not_match():
    issue = {"issue_id": "x", "type": "payment_allocation", "affected_ids": ["i1"], "expected_amount_minor": 20, "currency": "KZT", "allowed_evidence_sets": [["d1"]]}
    finding = {"type": "payment_allocation", "affected_ids": ["i1"], "claimed_amount_minor": 20, "currency": "KZT", "evidence_ids": ["d1"], "explanation": ""}
    for changed in (dict(finding, currency="USD"), dict(finding, claimed_amount_minor=21), dict(finding, evidence_ids=["d1", "invented"])):
        assert evaluate([issue], [changed], {"i1", "d1"}, 0)["tp"] == 0


def test_malformed_submission_is_rejected_without_exceptions():
    from ledgergym.score import validate_submission
    finding = {"type": [], "affected_ids": ["i1"], "claimed_amount_minor": 20, "currency": "KZT", "evidence_ids": ["d1"], "explanation": ""}
    assert not validate_submission({"episode_id": "e", "findings": [finding]}, "e")
