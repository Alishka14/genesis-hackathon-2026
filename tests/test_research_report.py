"""End-to-end evaluator-only diagnostics: 20 episodes, privacy, score parity."""
import json

from ledgergym.company_dataset import create_company_dataset
from ledgergym.research_report import analyse_development_dataset


def test_research_report_stays_aggregate_and_consistent_with_baselines(tmp_path):
    dataset = tmp_path / "development"
    create_company_dataset(
        dataset, seed=2026, include_settlement_hard_negatives=True)
    report = analyse_development_dataset(dataset, tmp_path / "report", trials=2)
    assert report["episodes"] == 20
    assert report["private_truth_exported"] is False
    assert report["official_score_modified"] is False
    assert report["contest_certified"] is False
    assert report["clean_case_counts"] == {
        "standard": 2, "hard_negative": 2, "faulty": 16,
    }
    assert report["faa_opportunity_unit"] == "validated_unimplicated_payment_operation"
    rec = report["policies"]["reconciliation"]
    assert rec["tp"] == 42
    assert rec["fp"] == 0
    assert rec["fn"] == 0
    assert rec["score_matches"] == 20
    assert rec["invariance_trials_passed"] == 40
    # Operation-level denominators include validated payments in faulty episodes,
    # not just one opportunity per fully clean company.
    assert rec["standard_opportunities"] > report["clean_case_counts"]["standard"]
    assert rec["hard_negative_opportunities"] >= report["clean_case_counts"]["hard_negative"]
    assert rec["standard_valid_case_fpr"] == 0
    assert rec["hard_negative_case_fpr"] == 0
    rnd = report["policies"]["seeded_random"]
    attacker = report["policies"]["mark_all"]
    assert rnd["fp"] == 20
    assert attacker["fp"] == 600
    for policy in ("oracle", "mark_all", "seeded_random", "reconciliation"):
        data = report["policies"][policy]
        assert sum(data["faa"].values()) == data["fp"]
        assert data["invariance_trials_passed"] == 40
    file = tmp_path / "report" / "research_summary.json"
    raw = file.read_text(encoding="utf-8")
    again = json.loads(raw)
    assert again == report
    for forbidden in (
        '"issue_id"', '"allowed_evidence_sets"', '"truth"',
        '"provenance"', '"seed"', '"private_pair_index"',
    ):
        assert forbidden not in raw
