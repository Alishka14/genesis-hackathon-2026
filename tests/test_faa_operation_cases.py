"""P1 FAA: valid payment-operation labels in mixed faulted development episodes."""
import copy

from ledgergym.company_world import build_company
from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.settlement_faults_v2 import build_settlement_fault_episode
from ledgergym.faa_operation_cases import verified_payment_operations
from ledgergym.research_diagnostics import false_accusation_analysis
from ledgergym.score import accessible_evidence_ids, evaluate


def _good_finding(issue):
    return {
        "type": issue["type"],
        "affected_ids": list(issue["affected_ids"]),
        "claimed_amount_minor": issue["expected_amount_minor"],
        "currency": issue["currency"],
        "evidence_ids": list(issue["allowed_evidence_sets"][0]),
        "explanation": "",
    }


def _wrong_finding(ids, document):
    return {
        "type": "reporting_period",
        "affected_ids": list(ids),
        "claimed_amount_minor": 777,
        "currency": "KZT",
        "evidence_ids": [document],
        "explanation": "",
    }


def test_v1_faulted_episode_has_real_clean_payment_opportunities():
    public, truth, _ = build_company(
        2026, {"postings": 200, "documents": 20,
               "faults": {"payment_allocation": 1}})
    cases = verified_payment_operations(public, truth)
    assert cases
    assert all(case["kind"] == "STANDARD_VALID" for case in cases.values())
    truth_ids = {identifier for issue in truth["issues"]
                 for identifier in issue["affected_ids"]}
    assert all(not truth_ids.intersection(case["affected_ids"])
               for case in cases.values())
    assert all(set(case["affected_ids"]) <= accessible_evidence_ids(public)
               for case in cases.values())
    assert len(cases) < len(public["tables"]["payments"])


def test_standard_valid_wrong_claim_in_mixed_episode_preserves_score():
    public, truth, _ = build_company(
        2026, {"postings": 200, "documents": 20,
               "faults": {"payment_allocation": 1}})
    annotations = verified_payment_operations(public, truth)
    pid, label = next(iter(annotations.items()))
    payment = next(p for p in public["tables"]["payments"]
                   if p["payment_id"] == pid)
    findings = [_good_finding(truth["issues"][0]),
                _wrong_finding(label["affected_ids"], payment["doc_id"])]
    public_ids = accessible_evidence_ids(public)
    official = evaluate(truth["issues"], findings, public_ids, 5)
    faa = false_accusation_analysis(
        truth["issues"], findings, public_ids,
        case_annotations=annotations, inspection_steps=5)
    assert official["tp"] == official["fp"] == 1
    assert faa["fp_subtypes"]["FP_standard_valid"] == 1
    assert faa["fp_classification_by_finding"] == [None, "FP_standard_valid"]
    assert faa["official_reward_unchanged"] == official["reward"]
    assert sum(faa["fp_subtypes"].values()) == official["fp"]


def test_issue_implicated_wrong_claim_stays_unattributed():
    public, truth, _ = build_company(
        2026, {"postings": 200, "documents": 20,
               "faults": {"payment_allocation": 1}})
    annotations = verified_payment_operations(public, truth)
    pid, label = next(iter(annotations.items()))
    payment = next(p for p in public["tables"]["payments"]
                   if p["payment_id"] == pid)
    accusation = _wrong_finding(
        [truth["issues"][0]["affected_ids"][0], pid],
        payment["doc_id"])
    public_ids = accessible_evidence_ids(public)
    score = evaluate(truth["issues"], [accusation], public_ids, 1)
    result = false_accusation_analysis(
        truth["issues"], [accusation], public_ids,
        case_annotations=annotations, inspection_steps=1)
    assert result["fp_classification_by_finding"] == ["FP_unattributed"]
    assert result["fp_subtypes"]["FP_standard_valid"] == 0
    assert result["official_reward_unchanged"] == score["reward"]


def test_v2_split_and_refund_get_separate_hard_negative_opportunities():
    public, truth, _ = build_settlement_company(
        2026, {"postings": 200, "documents": 20})
    cases = verified_payment_operations(public, truth)
    hard = [case for case in cases.values()
            if case["kind"] == "SUSPICIOUS_BUT_VALID"]
    assert len(hard) == 2
    assert len(cases) > len(hard)
    assert all("affected_ids" in case for case in hard)
    split = next(p for p in public["tables"]["payments"]
                 if p["kind"] == "payment" and "allocation_basis" in p)
    refund = next(p for p in public["tables"]["payments"]
                  if p["kind"] == "refund")
    assert split["payment_id"] in cases
    assert refund["payment_id"] in cases


def test_v2_faulted_split_is_excluded_but_clean_refund_remains():
    public, truth, _ = build_settlement_fault_episode(
        2026, {"postings": 200, "documents": 20,
               "fault": "payment_allocation"})
    cases = verified_payment_operations(public, truth)
    refund = next(p for p in public["tables"]["payments"]
                  if p["kind"] == "refund")
    split = next(p for p in public["tables"]["payments"]
                 if "allocation_basis" in p)
    assert refund["payment_id"] in cases
    assert cases[refund["payment_id"]]["kind"] == "SUSPICIOUS_BUT_VALID"
    assert split["payment_id"] not in cases
    assert all(not (set(case["affected_ids"])
                    & set(truth["issues"][0]["affected_ids"]))
               for case in cases.values())


def test_ambiguous_overlap_not_counted_twice():
    public_ids = {"pay-a", "pay-b", "inv-one", "doc"}
    annotations = {
        "pay-a": {"kind": "STANDARD_VALID", "affected_ids": ["pay-a", "inv-one"]},
        "pay-b": {"kind": "SUSPICIOUS_BUT_VALID",
                  "affected_ids": ["pay-b", "inv-one"]},
    }
    finding = _wrong_finding(["inv-one"], "doc")
    baseline = evaluate([], [finding], public_ids, 0)
    report = false_accusation_analysis(
        [], [finding], public_ids, case_annotations=annotations)
    assert report["fp_subtypes"]["FP_unattributed"] == 1
    assert report["case_level"]["standard_valid_case_fpr"]["cases_with_fp"] == 0
    assert report["case_level"]["hard_negative_case_fpr"]["cases_with_fp"] == 0
    assert report["official_reward_unchanged"] == baseline["reward"]


def test_malformed_or_duplicate_public_payment_ids_rejected():
    public, truth, _ = build_company(
        2026, {"postings": 200, "documents": 20})
    bad = copy.deepcopy(public)
    bad["tables"]["payments"].append(copy.deepcopy(bad["tables"]["payments"][0]))
    try:
        verified_payment_operations(bad, truth)
    except ValueError as exc:
        assert "duplicate or malformed" in str(exc)
    else:
        raise AssertionError("duplicate payment ID was accepted")
