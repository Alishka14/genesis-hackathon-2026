"""Causal counterpair tests: clean and faulty v2 share a public policy/schema.

Both variants provide an actual six-file episode and an independently
derived public evidence chain; private labels stay outside the agent view.
"""
import copy
import json

import pytest

import judge_adapter
from ledgergym.baselines import run_baseline
from ledgergym.company_checks_v2 import validate_settlement_company
from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.episode_io import export_episode, load_public_episode
from ledgergym.generator import generate_episode
from ledgergym.score import accessible_evidence_ids, evaluate
from ledgergym.settlement_faults_v2 import (
    build_settlement_fault_episode, inspect_settlement_faults,
    validate_settlement_episode,
)


MODES = ("duplicate_invoice", "payment_allocation", "duplicate_allocation")


def _find_intervention_target(public, intervention):
    table = intervention["table"]
    if table == "invoices.line_items":
        rows = [line for invoice in public["tables"]["invoices"]
                for line in invoice["line_items"]]
        key = "line_id"
    elif table == "payments":
        rows = public["tables"]["payments"]
        key = "payment_id"
    else:
        raise AssertionError("unauthorized intervention " + table)
    matches = [r for r in rows if r[key] == intervention["id"]]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", [7, 81, 2026])
@pytest.mark.parametrize("postings,documents", [(200, 20), (400, 80), (2000, 200)])
def test_v2_clean_and_fault_are_reversible_documented_business_changes(
        mode, seed, postings, documents):
    size = {"postings": postings, "documents": documents}
    clean, clean_truth, _ = build_settlement_company(seed, size)
    faulty, truth, provenance = build_settlement_fault_episode(
        seed, {**size, "fault": mode})
    assert clean_truth == {"issues": []}
    assert clean["manifest"] == faulty["manifest"]
    assert clean["policy"] == faulty["policy"]
    assert clean["manifest"]["schema_version"] == "0.4-company-settlements"
    assert len(clean["tables"]["ledger"]) == len(faulty["tables"]["ledger"]) == postings
    assert sum(r["debit_minor"] - r["credit_minor"]
               for r in faulty["tables"]["ledger"]) == 0
    assert len(clean["tables"]["invoices"]) + len(clean["tables"]["payments"]) == documents
    assert faulty["tables"]["ledger"] == clean["tables"]["ledger"]
    assert faulty["tables"]["fx"] == clean["tables"]["fx"]
    service_edits = [i for i in provenance["interventions"]
                     if i["table"] == "invoices.line_items"]
    allocation_edits = [i for i in provenance["interventions"]
                        if i["table"] == "payments"]
    if mode in ("duplicate_invoice", "duplicate_allocation"):
        # A single economic service identity may be repeated across MANY
        # line items when an episode contains 2,000 postings.
        assert service_edits
        assert len({i["after"] for i in service_edits}) == 1
    else:
        assert not service_edits
    assert len(allocation_edits) == int(mode in (
        "payment_allocation", "duplicate_allocation"))
    assert len(provenance["interventions"]) == len(service_edits) + len(allocation_edits)
    assert {i["type"] for i in truth["issues"]} == (
        {"duplicate_invoice", "payment_allocation"}
        if mode == "duplicate_allocation" else {mode})
    assert len(truth["issues"]) == (2 if mode == "duplicate_allocation" else 1)

    # A complete reverse of recorded changes must reproduce the exact clean
    # episode, including IDs, remittance schedules, row order and balances.
    restored = copy.deepcopy(faulty)
    for intervention in reversed(provenance["interventions"]):
        target = _find_intervention_target(restored, intervention)
        assert target[intervention["field"]] == intervention["after"]
        target[intervention["field"]] = copy.deepcopy(intervention["before"])
    assert restored == clean
    assert validate_settlement_company(clean, clean_truth)["refunds"] == 1
    assert validate_settlement_episode(faulty, truth)["issue_count"] == len(truth["issues"])

    # Observed findings are derived by public-only audit, never by reading
    # the secret truth generated alongside the altered episode.
    findings = inspect_settlement_faults(faulty)
    public_ids = accessible_evidence_ids(faulty)
    assert len(findings) == len(truth["issues"])
    for finding in findings:
        assert 0 < len(finding["evidence_ids"]) <= 10
        assert set(finding["affected_ids"]) <= public_ids
        assert set(finding["evidence_ids"]) <= public_ids
        matching = [
            i for i in truth["issues"] if i["type"] == finding["type"]
            and set(i["affected_ids"]) == set(finding["affected_ids"])
            and i["expected_amount_minor"] == finding["claimed_amount_minor"]
            and i["currency"] == finding["currency"]
        ]
        assert len(matching) == 1
        assert any(set(group) <= set(finding["evidence_ids"])
                   for group in matching[0]["allowed_evidence_sets"])
    result = evaluate(truth["issues"], findings, public_ids, inspection_steps=0)
    assert (result["tp"], result["fp"], result["fn"], result["f1"], result["reward"]) == (
        len(findings), 0, 0, 1, 1)
    assert evaluate(truth["issues"], [], public_ids, inspection_steps=0)["f1"] == 0
    assert inspect_settlement_faults(clean) == []
    assert "private-" not in json.dumps(faulty)


@pytest.mark.parametrize("mode", MODES)
def test_v2_replay_and_score_are_deterministic(mode):
    config = {"postings": 400, "documents": 80, "fault": mode}
    a = build_settlement_fault_episode(17, config)
    b = build_settlement_fault_episode(17, config)
    assert a == b
    assert a[0] != build_settlement_fault_episode(18, config)[0]
    assert a[0]["policy"] == build_settlement_company(17, {
        "postings": 400, "documents": 80})[0]["policy"]


@pytest.mark.parametrize("mode", MODES)
def test_canonical_judge_accepts_evidence_backed_v2_findings(mode, tmp_path):
    output = tmp_path / mode
    judge_adapter.generate_episode(
        7, {"scenario": "company_settlement_fault",
            "postings": 200, "documents": 20, "fault": mode}, output)
    public = load_public_episode(output / "public")
    truth = json.loads((output / "private" / "truth.json").read_text())
    findings = inspect_settlement_faults(public)
    assert len(findings) == len(truth["issues"])
    assert public["policy"] == build_settlement_company(7, {
        "postings": 200, "documents": 20})[0]["policy"]
    env = judge_adapter.make_env()
    obs, info = env.reset(19, {"mode": "closed", "episode_dir": str(output),
                               "team_config": {}})
    assert info == {}
    assert "truth" not in json.dumps(obs)
    evidence_id = findings[0]["evidence_ids"][0]
    # All finding evidence must be addressable, not leaked through info.
    assert evidence_id in accessible_evidence_ids(public)
    _, terminal_reward, terminated, truncated, private_info = env.step({
        "name": "submit",
        "args": {"findings": {"episode_id": obs["manifest"]["episode_id"],
                              "findings": findings}},
    })
    assert terminated and not truncated and terminal_reward == 0
    assert private_info == {}
    assert env.final_score["tp"] == len(findings)
    assert env.final_score["fp"] == env.final_score["fn"] == 0
    assert env.final_score["f1"] == 1
    assert env.final_score["return"] == 1


@pytest.mark.parametrize("mode", MODES)
def test_reconciliation_is_public_only_and_does_not_overaccuse(mode):
    clean, clean_truth, _ = build_settlement_company(81, {
        "postings": 200, "documents": 20})
    faulty, truth, _ = build_settlement_fault_episode(81, {
        "postings": 200, "documents": 20, "fault": mode})
    for public, expected in [(clean, clean_truth), (faulty, truth)]:
        result = run_baseline(public, expected, "reconciliation")
        assert result["score"]["tp"] == len(expected["issues"])
        assert result["score"]["fp"] == result["score"]["fn"] == 0
        assert result["score"]["f1"] == 1
        assert len(result["trajectory"]) <= 100


@pytest.mark.parametrize("mode", MODES)
def test_empty_or_lying_v2_truth_is_rejected(mode, tmp_path):
    public, truth, provenance = build_settlement_fault_episode(81, {
        "postings": 200, "documents": 20, "fault": mode})
    with pytest.raises(ValueError, match="truth"):
        validate_settlement_episode(public, {"issues": []})
    with pytest.raises(ValueError):
        export_episode(tmp_path / "mislabel", public, {"issues": []},
                       seed=81, provenance=provenance)
    assert not (tmp_path / "mislabel").exists()
    fake = copy.deepcopy(truth)
    fake["issues"][0]["expected_amount_minor"] += 10
    with pytest.raises(ValueError, match="truth"):
        validate_settlement_episode(public, fake)


@pytest.mark.parametrize("mode", MODES)
def test_causal_pair_handles_unrelated_ledger_corruption_without_exonerating(mode):
    public, truth, _ = build_settlement_fault_episode(7, {
        "postings": 200, "documents": 20, "fault": mode})
    corrupted = copy.deepcopy(public)
    row = next(x for x in corrupted["tables"]["ledger"] if x["debit_minor"] > 0)
    row["debit_minor"] += 1
    with pytest.raises(ValueError, match="balanced"):
        validate_settlement_episode(corrupted, truth)


def test_v2_faulted_generator_route_and_versioned_roundtrip(tmp_path):
    config = {"scenario": "company_settlement_fault", "postings": 200,
              "documents": 20, "fault": "duplicate_allocation"}
    public, truth = generate_episode(81, config)
    assert len(truth["issues"]) == 2
    full, full_truth, provenance = build_settlement_fault_episode(81, {
        "postings": 200, "documents": 20, "fault": "duplicate_allocation"})
    assert (public, truth) == (full, full_truth)
    target = tmp_path / "faulty"
    export_episode(target, full, full_truth, seed=81, provenance=provenance)
    assert load_public_episode(target / "public") == full
    assert json.loads((target / "private" / "truth.json").read_text()) == truth
    assert validate_settlement_episode(full, truth)["issue_count"] == 2


@pytest.mark.parametrize("config", [
    {}, {"postings": 200, "documents": 20},
    {"postings": 200, "documents": 20, "fault": "fx_rate_or_date"},
    {"postings": 200, "documents": 20, "fault": ""},
    {"postings": 200, "documents": 20, "fault": True},
    {"postings": 200, "documents": 20, "fault": "payment_allocation", "unexpected": 1},
])
def test_v2_fault_generator_rejects_unknown_configuration(config):
    with pytest.raises(ValueError):
        build_settlement_fault_episode(81, config)
