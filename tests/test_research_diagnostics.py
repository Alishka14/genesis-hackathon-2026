"""Evaluator-only EQT / FAA: exact-matcher parity and no reward mutation."""
import copy
import random

import pytest

from ledgergym.research_diagnostics import (
    evidence_taxonomy, false_accusation_analysis, exact_matching,
)
from ledgergym.score import evaluate


def _case():
    issue = {
        "issue_id": "secret-issue-1", "type": "duplicate_invoice",
        "affected_ids": ["inv-a", "inv-b"],
        "expected_amount_minor": 12500, "currency": "KZT",
        "allowed_evidence_sets": [["doc-a", "doc-b"], ["row-a", "row-b"]],
    }
    finding = {
        "type": "duplicate_invoice", "affected_ids": ["inv-a", "inv-b"],
        "claimed_amount_minor": 12500, "currency": "KZT",
        "evidence_ids": ["doc-a", "doc-b"], "explanation": "",
    }
    public = {
        "inv-a", "inv-b", "doc-a", "doc-b", "row-a", "row-b",
        "unrelated", "pmt-std", "pmt-hard", "doc-std", "doc-hard",
    }
    return issue, finding, public


def test_eqt_full_chain_can_coexist_with_irrelevant_extra():
    issue, finding, public = _case()
    finding["evidence_ids"].append("unrelated")
    before = evaluate([issue], [finding], public, 3)
    report = evidence_taxonomy([issue], [finding], public)
    assert report["items"][0] == ["SUFFICIENT", "IRRELEVANT_EVIDENCE"]
    assert report["counts"]["SUFFICIENT"] == 1
    assert evaluate([issue], [finding], public, 3) == before
    assert before["tp"] == 1
    assert before["reward"] == pytest.approx(.994)


def test_eqt_incomplete_fabricated_temporal_and_contradiction():
    issue, finding, public = _case()
    missing = copy.deepcopy(finding)
    missing["evidence_ids"] = ["doc-a"]
    forged = copy.deepcopy(finding)
    forged["evidence_ids"] = ["doc-a", "fake-secret-doc"]
    unrelated = copy.deepcopy(finding)
    unrelated["type"] = "payment_allocation"
    tagged = copy.deepcopy(finding)
    tagged["evidence_ids"] = ["row-a", "row-b"]
    report = evidence_taxonomy(
        [issue], [missing, forged, unrelated, tagged], public,
        temporally_invalid_ids=["row-a"],
        contradictory_ids=["row-b"],
    )
    assert "INCOMPLETE_CHAIN" in report["items"][0]
    assert "FABRICATED_ID" in report["items"][1]
    assert "INCOMPLETE_CHAIN" in report["items"][1]
    assert report["items"][2] == ["UNDETERMINED"]
    assert report["items"][3] == [
        "SUFFICIENT", "TEMPORALLY_INVALID", "CONTRADICTORY_EVIDENCE"]
    with pytest.raises(ValueError):
        evidence_taxonomy(
            [issue], [finding], public,
            temporally_invalid_ids=["non-public-date"],
        )


def test_faa_exact_partition_and_case_level_rates():
    issue, correct, public = _case()
    hard = {
        **correct, "type": "payment_allocation",
        "affected_ids": ["pmt-hard"],
        "evidence_ids": ["doc-hard"],
    }
    standard = {
        **correct, "type": "payment_allocation",
        "affected_ids": ["pmt-std"],
        "evidence_ids": ["doc-std"],
    }
    fake = {
        **correct, "affected_ids": ["private-guess"],
        "evidence_ids": ["missing-doc"],
    }
    findings = [correct, copy.deepcopy(correct), hard, standard, fake]
    labelled = {
        "hard-case-1": {
            "kind": "SUSPICIOUS_BUT_VALID", "affected_ids": ["pmt-hard"],
        },
        "standard-case-1": {
            "kind": "STANDARD_VALID", "affected_ids": ["pmt-std"],
        },
    }
    score_before = evaluate([issue], findings, public, 8)
    report = false_accusation_analysis(
        [issue], findings, public, case_annotations=labelled,
        inspection_steps=8,
    )
    assert report["fp_subtypes"] == {
        "FP_standard_valid": 1,
        "FP_hard_negative": 1,
        "FP_duplicate": 1,
        "FP_unattributed": 1,
    }
    assert report["fp_classification_by_finding"] == [
        None, "FP_duplicate", "FP_hard_negative",
        "FP_standard_valid", "FP_unattributed",
    ]
    assert report["official_fp"] == score_before["fp"] == 4
    assert report["rates"] == {
        "standard_valid_case_fpr": 1.0,
        "hard_negative_case_fpr": 1.0,
    }
    assert report["official_reward_unchanged"] == score_before["reward"]
    assert evaluate([issue], findings, public, 8) == score_before


def test_faa_case_level_denom_is_none_not_zero_without_annotations():
    issue, correct, public = _case()
    result = false_accusation_analysis(
        [issue], [correct], public,
    )
    assert result["official_fp"] == 0
    assert result["rates"] == {
        "standard_valid_case_fpr": None,
        "hard_negative_case_fpr": None,
    }
    assert set(result["fp_subtypes"].values()) == {0}
    assert result["fp_classification_by_finding"] == [None]


def test_matching_matches_official_score_for_order_permutations():
    issue, correct, public = _case()
    duplicates = [correct, copy.deepcopy(correct)]
    baseline = evaluate([issue], duplicates, public, 2)
    rng = random.Random(2026)
    for _ in range(30):
        rng.shuffle(duplicates)
        for f in duplicates:
            rng.shuffle(f["affected_ids"])
            rng.shuffle(f["evidence_ids"])
        matched, edges = exact_matching([issue], duplicates, public)
        assert len(matched) == baseline["tp"] == 1
        assert len(edges) == 2
        assert evaluate([issue], duplicates, public, 2) == baseline
        assert sum(false_accusation_analysis(
            [issue], duplicates, public)["fp_subtypes"].values()
        ) == baseline["fp"] == 1


def test_bad_case_annotations_fail_closed():
    issue, correct, public = _case()
    with pytest.raises(ValueError):
        false_accusation_analysis(
            [issue], [correct], public,
            case_annotations={
                "bad": {
                    "kind": "SUSPICIOUS_BUT_VALID",
                    "affected_ids": ["private-unknown"],
                },
            },
        )
