"""Acceptance tests for versioned six-file split + supplier refund episodes."""
from __future__ import annotations

import copy
import json

import pytest

import judge_adapter
from ledgergym.canonical import score_episode
from ledgergym.company_world import build_company
from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.company_checks_v2 import validate_settlement_company
from ledgergym.episode_io import export_episode, load_public_episode
from ledgergym.generator import generate_episode
from ledgergym.refund_settlement import apply_refunds


@pytest.mark.parametrize("postings,documents", [(200, 20), (400, 80), (2000, 200)])
@pytest.mark.parametrize("seed", [7, 81, 2026])
def test_full_company_split_refund_ledger_and_document_evidence(seed, postings, documents):
    config = {"postings": postings, "documents": documents}
    public, truth, provenance = build_settlement_company(seed, config)
    assert truth == {"issues": []}
    assert len(public["tables"]["ledger"]) == postings
    assert len(public["tables"]["invoices"]) + len(public["tables"]["payments"]) == documents
    assert public["policy"]["accounting_model"] == "accrual_company_v2"
    assert public["manifest"]["schema_version"] == "0.4-company-settlements"
    assert sum(r["debit_minor"] - r["credit_minor"] for r in public["tables"]["ledger"]) == 0
    assert len(provenance["clean_cases"]) == 2
    report = validate_settlement_company(public, truth)
    assert report["split_payments"] >= 1
    assert report["refunds"] == 1
    assert public == build_settlement_company(seed, config)[0]
    assert truth == build_settlement_company(seed, config)[1]
    assert public != build_settlement_company(seed + 1, config)[0]

    payments = public["tables"]["payments"]
    by_id = {p["payment_id"]: p for p in payments}
    refund = next(p for p in payments if p["kind"] == "refund")
    splits = [p for p in payments if p["kind"] == "payment" and len(p["invoice_refs"]) > 1]
    assert splits and splits[0]["remittance_invoice_id"] is None
    origin = by_id[refund["original_payment_id"]]
    assert origin["kind"] == "payment" and refund["currency"] == origin["currency"]
    assert refund["invoice_refs"][0]["invoice_id"] in {
        r["invoice_id"] for r in origin["invoice_refs"]
    }
    docs = {x["doc_id"] for x in public["tables"]["invoices"] + payments}
    rows = {x["row_id"] for x in public["tables"]["ledger"]}
    assert origin["doc_id"] in docs and refund["doc_id"] in docs
    assert len([r for r in public["tables"]["ledger"]
                if r["payment_id"] == refund["payment_id"] and r["row_id"] in rows]) == 2

    # Cross-check against an independently developed internal reconciliation
    # module, without using the private truth to calculate the paid balances.
    ordinary = [p for p in payments if p["kind"] == "payment"]
    refund_input = [{
        "refund_id": refund["payment_id"], "kind": "refund",
        "original_payment_id": refund["original_payment_id"],
        "entity_id": refund["entity_id"], "currency": refund["currency"],
        "timestamp": refund["timestamp"], "amount_minor": refund["amount_minor"],
        "invoice_refs": copy.deepcopy(refund["invoice_refs"]),
    }]
    settled = apply_refunds(public["tables"]["invoices"], ordinary, refund_input)
    assert settled["invoice_balances"] == report["balances"]

    serialized = json.dumps(public, ensure_ascii=False)
    assert "provenance" not in serialized and "allowed_evidence_sets" not in serialized
    assert "original_payment_id" in serialized  # public proof of a refund's source


def test_versioned_roundtrip_six_public_files_and_separate_private_provenance(tmp_path):
    seed = 81
    public, truth, provenance = build_settlement_company(seed, {"postings": 200, "documents": 20})
    target = tmp_path / "episode"
    export_episode(target, public, truth, seed=seed, provenance=provenance)
    assert {x.name for x in (target / "public").iterdir()} == {
        "manifest.json", "policy.json", "ledger.csv", "fx.csv", "payments.jsonl", "invoices.jsonl"
    }
    assert {x.name for x in (target / "private").iterdir()} == {"truth.json", "provenance.json"}
    assert load_public_episode(target / "public") == public
    report = validate_settlement_company(load_public_episode(target / "public"), truth)
    assert report["split_payments"] >= 1 and report["refunds"] == 1
    assert json.loads((target / "private" / "truth.json").read_text()) == truth
    assert json.loads((target / "private" / "provenance.json").read_text()) == provenance
    assert score_episode(target, {"episode_id": public["manifest"]["episode_id"],
                                  "findings": []}, inspection_steps=0)["return"] == 1.0


def test_canonical_closed_judge_can_inspect_refund_and_split_without_truth(tmp_path):
    root = tmp_path / "judge-episode"
    judge_adapter.generate_episode(17, {"scenario": "company_settlements",
                                        "postings": 200, "documents": 20}, root)
    public = load_public_episode(root / "public")
    refund = next(p for p in public["tables"]["payments"] if p["kind"] == "refund")
    env = judge_adapter.make_env()
    first, info = env.reset(123, {"mode": "closed", "episode_dir": str(root), "team_config": {}})
    assert info == {} and first["manifest"]["schema_version"] == "0.4-company-settlements"
    obs, reward, terminated, truncated, public_info = env.step(
        {"name": "get_document", "args": {"doc_id": refund["doc_id"]}}
    )
    assert obs["result"]["kind"] == "refund" and obs["result"]["original_payment_id"] == refund["original_payment_id"]
    assert reward == 0 and not terminated and not truncated and public_info == {}
    ledger_row = next(r for r in public["tables"]["ledger"]
                      if r["payment_id"] == refund["payment_id"])
    obs, reward, terminated, truncated, public_info = env.step(
        {"name": "get_record", "args": {"table": "ledger", "id": ledger_row["row_id"]}}
    )
    assert obs["result"]["row_id"] == ledger_row["row_id"] and public_info == {}
    response, reward, terminated, truncated, public_info = env.step(
        {"name": "submit", "args": {"findings": {
            "episode_id": first["manifest"]["episode_id"], "findings": []
        }}}
    )
    assert terminated and not truncated and reward == 0 and public_info == {}
    assert env.final_score["f1"] == 1 and env.final_score["return"] == pytest.approx(0.996)


def test_generator_scenario_returns_clean_versioned_episodes():
    config = {"scenario": "company_settlements", "postings": 200, "documents": 20}
    public, truth = generate_episode(29, config)
    assert truth == {"issues": []}
    assert validate_settlement_company(public, truth)["refunds"] == 1
    # Earlier four-fault generator remains compatible and unchanged.
    original, original_truth, _ = build_company(29, {"postings": 200, "documents": 20})
    from ledgergym.company_checks import validate_company
    assert original["policy"]["accounting_model"] == "accrual_company_v1"
    validate_company(original, original_truth)


@pytest.mark.parametrize("key", ["faults", "compounds", "unknown"])
def test_v2_cannot_silently_accept_unsupported_fault_configuration(key):
    with pytest.raises(ValueError):
        build_settlement_company(7, {key: {"duplicate_invoice": 1}})


@pytest.mark.parametrize("variant", [
    "duplicate_refund_source", "refund_exceeds_original", "refund_ledger_not_reversed",
    "refund_entity_mismatch", "split_amount_mismatch", "broken_invoice_amount",
    "false_duplicate_truth", "underfunded_bank"
])
def test_validator_detects_published_financial_inconsistencies(variant):
    public, truth, _ = build_settlement_company(81, {"postings": 200, "documents": 20})
    public = copy.deepcopy(public)
    truth = copy.deepcopy(truth)
    refund = next(p for p in public["tables"]["payments"] if p["kind"] == "refund")
    split = next(p for p in public["tables"]["payments"]
                 if p["kind"] == "payment" and len(p["invoice_refs"]) == 2)
    if variant == "duplicate_refund_source":
        refund["original_payment_id"] = split["payment_id"]
    elif variant == "refund_exceeds_original":
        source = next(p for p in public["tables"]["payments"]
                      if p["payment_id"] == refund["original_payment_id"])
        refund["amount_minor"] = source["amount_minor"] + 1
        refund["invoice_refs"][0]["amount_minor"] = refund["amount_minor"]
    elif variant == "refund_ledger_not_reversed":
        bank = next(r for r in public["tables"]["ledger"] if
                    r["payment_id"] == refund["payment_id"] and r["account"] == "bank")
        bank["debit_minor"], bank["credit_minor"] = 0, bank["debit_minor"]
    elif variant == "refund_entity_mismatch":
        refund["entity_id"] = "counterfeit-entity"
    elif variant == "split_amount_mismatch":
        split["invoice_refs"][0]["amount_minor"] -= 1
    elif variant == "broken_invoice_amount":
        public["tables"]["invoices"][0]["line_items"][0]["amount_minor"] += 1
    elif variant == "false_duplicate_truth":
        truth["issues"] = [{"issue_id": "fake"}]
    else:
        bank = next(x for x in public["tables"]["ledger"]
                    if x["payment_id"] is None and x["invoice_id"] is None and x["account"] == "bank")
        bank["debit_minor"] = 1
    with pytest.raises(ValueError):
        validate_settlement_company(public, truth)


def test_private_provenance_is_mandatory_for_versioned_export(tmp_path):
    public, truth, provenance = build_settlement_company(81, {"postings": 200, "documents": 20})
    with pytest.raises(ValueError, match="provenance"):
        export_episode(tmp_path / "bad", public, truth, seed=81)
    wrong = copy.deepcopy(provenance)
    wrong["seed"] = 7
    with pytest.raises(ValueError, match="provenance"):
        export_episode(tmp_path / "bad-2", public, truth, seed=81, provenance=wrong)
    assert not (tmp_path / "bad").exists()
    assert not (tmp_path / "bad-2").exists()
