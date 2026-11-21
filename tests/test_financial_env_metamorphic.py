"""Full public API metamorphic regression, not scorer-only equality.

Exercises reset, cursor pagination, get_record, get_document, calculator, and
submit on generated public companies before/after CAB's bijective renaming
and row shuffling. Uses private truth only in the trusted *test evaluator*.
"""
import json

import pytest

from ledgergym.company_world import build_company
from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.settlement_faults_v2 import build_settlement_fault_episode
from ledgergym.cab_invariance import transform_financial_episode
from ledgergym.env import LedgerSandbox
from ledgergym.score import accessible_evidence_ids, evaluate
from ledgergym.baselines import run_baseline
from ledgergym.independent_finance_audit import audit_company


def _drive_oracle(public, truth):
    ids = accessible_evidence_ids(public)
    env = LedgerSandbox(
        public, lambda findings, steps: evaluate(truth["issues"], findings, ids, steps))
    initial, _ = env.reset()
    assert initial["manifest"]["episode_id"] == public["manifest"]["episode_id"]
    assert "seed" not in json.dumps(initial)
    assert "truth" not in json.dumps(initial)
    fetched = []
    cursor = None
    page_requests = 0
    while True:
        action = {"action": "list_records", "table": "invoices", "limit": 13}
        if cursor is not None:
            action["cursor"] = cursor
        obs, reward, term, trunc, _ = env.step(action)
        assert reward == 0 and not term and not trunc and "records" in obs
        fetched.extend(row["invoice_id"] for row in obs["records"])
        page_requests += 1
        cursor = obs["next_cursor"]
        if cursor is None:
            break
        assert page_requests <= 16
    assert set(fetched) == {row["invoice_id"] for row in public["tables"]["invoices"]}
    assert len(fetched) == len(set(fetched)) == len(public["tables"]["invoices"])
    invoice = public["tables"]["invoices"][0]
    obs, reward, term, trunc, _ = env.step({
        "action": "get_record", "table": "invoices", "id": invoice["invoice_id"]})
    assert obs["record"]["doc_id"] == invoice["doc_id"]
    assert reward == 0 and not term and not trunc
    doc, reward, term, trunc, _ = env.step({
        "action": "get_document", "doc_id": invoice["doc_id"]})
    assert doc["document"]["invoice_id"] == invoice["invoice_id"]
    assert reward == 0 and not term and not trunc
    calc, reward, term, trunc, _ = env.step({
        "action": "calculator", "expression": "101/2"})
    assert calc["value"] == "50.5"
    assert reward == 0 and not term and not trunc
    findings = [{
        "type": issue["type"],
        "affected_ids": list(issue["affected_ids"]),
        "claimed_amount_minor": issue["expected_amount_minor"],
        "currency": issue["currency"],
        "evidence_ids": list(issue["allowed_evidence_sets"][0]),
        "explanation": "Validated by source documents",
    } for issue in truth["issues"]]
    last, reward, term, trunc, info = env.step({
        "action": "submit", "episode_id": public["manifest"]["episode_id"],
        "findings": findings})
    assert term and not trunc and last["status"] == "finished"
    assert info["score"]["tp"] == len(truth["issues"])
    assert info["score"]["fp"] == info["score"]["fn"] == 0
    assert info["score"]["f1"] == 1
    assert reward == pytest.approx(1 - 0.002 * (page_requests + 3))
    return {
        "reward": reward, "score": info["score"],
        "inspection_steps": page_requests + 3,
        "records_observed": len(fetched),
        "read_actions": page_requests + 3,
    }


V1 = (
    {"faults": {"duplicate_invoice": 1}},
    {"faults": {"payment_allocation": 1}},
    {"faults": {"fx_rate_or_date": 1}},
    {"faults": {"reporting_period": 1}},
    {"compounds": {"fx_allocation": 1}},
    {"compounds": {"duplicate_allocation": 1}},
    {},
)


@pytest.mark.parametrize("seed", [7, 42, 2026])
@pytest.mark.parametrize("profile", V1)
def test_environment_oracle_remapping_invariance_v1(seed, profile):
    public, truth, _ = build_company(seed, {
        "postings": 200, "documents": 20, **profile})
    audit_company(public, truth)
    orig = _drive_oracle(public, truth)
    transformed, new_truth = transform_financial_episode(
        public, truth, seed=seed + 171)
    audit_company(transformed, new_truth)
    after = _drive_oracle(transformed, new_truth)
    assert after == orig
    assert run_baseline(public, truth, "reconciliation")["score"] == (
        run_baseline(transformed, new_truth, "reconciliation")["score"])
    assert run_baseline(public, truth, "oracle")["score"] == (
        run_baseline(transformed, new_truth, "oracle")["score"])


@pytest.mark.parametrize("seed", [7, 42, 2026])
@pytest.mark.parametrize("profile", [
    None, "duplicate_invoice", "payment_allocation", "duplicate_allocation",
])
def test_environment_oracle_remapping_invariance_v2(seed, profile):
    dims = {"postings": 200, "documents": 20}
    if profile is None:
        public, truth, _ = build_settlement_company(seed, dims)
    else:
        public, truth, _ = build_settlement_fault_episode(
            seed, {**dims, "fault": profile})
    audit_company(public, truth)
    orig = _drive_oracle(public, truth)
    transformed, new_truth = transform_financial_episode(public, truth, seed=seed + 171)
    audit_company(transformed, new_truth)
    assert _drive_oracle(transformed, new_truth) == orig
    assert run_baseline(public, truth, "oracle")["score"] == (
        run_baseline(transformed, new_truth, "oracle")["score"])


@pytest.mark.parametrize("offset", ["+03:00", "+09:00"])
@pytest.mark.parametrize("foreign", ["USD", "EUR"])
@pytest.mark.parametrize("month", ["2026-03", "2026-10"])
def test_environment_variants_are_end_to_end_action_compatible(offset, foreign, month):
    config = {"postings": 200, "documents": 20, "cutoff_timezone": offset,
              "foreign_currency": foreign, "period_month": month,
              "compounds": {"fx_allocation": 1}}
    public, truth, _ = build_company(1200, config)
    audit_company(public, truth)
    result = _drive_oracle(public, truth)
    assert result["score"]["tp"] == 2
    changed, changed_truth = transform_financial_episode(
        public, truth, seed=155)
    audit_company(changed, changed_truth)
    assert _drive_oracle(changed, changed_truth) == result
