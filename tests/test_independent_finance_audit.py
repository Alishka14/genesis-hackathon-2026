"""Independent financial audit and opt-in scenario diversification.

All tests derive synthetic examples using the public generator but recompute
expected issues and evidence by an evaluator-only *separate implementation*.
There is no claim these tests are organizers' blinded 20 episodes.
"""
import copy
from datetime import datetime

import pytest

from ledgergym.company_world import build_company
from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.settlement_faults_v2 import build_settlement_fault_episode
from ledgergym.independent_finance_audit import audit_company
from ledgergym.baselines import run_baseline


V1_PROFILES = (
    {},
    {"faults": {"duplicate_invoice": 1}},
    {"faults": {"payment_allocation": 1}},
    {"faults": {"fx_rate_or_date": 1}},
    {"faults": {"reporting_period": 1}},
    {"compounds": {"fx_allocation": 1}},
    {"compounds": {"duplicate_allocation": 1}},
    {"faults": {"duplicate_invoice": 2, "payment_allocation": 2,
                 "fx_rate_or_date": 2, "reporting_period": 2},
     "compounds": {"fx_allocation": 1, "duplicate_allocation": 1}},
)


@pytest.mark.parametrize("seed", [7, 42, 2026])
@pytest.mark.parametrize("profile", V1_PROFILES)
def test_independent_v1_audits_each_fault_and_compound(seed, profile):
    config = {"postings": 460, "documents": 60, **profile}
    public, truth, provenance = build_company(seed, config)
    report = audit_company(public, truth)
    assert report["status"] == "PASS"
    assert report["issues_audited"] == len(truth["issues"])
    assert report["journal_net_minor"] == 0
    assert provenance["clean_preflight"] == "passed"
    assert run_baseline(public, truth, "reconciliation")["score"]["fp"] == 0


@pytest.mark.parametrize("seed", [7, 42, 2026])
@pytest.mark.parametrize("fault", [None, "duplicate_invoice", "payment_allocation",
                                     "duplicate_allocation"])
def test_independent_v2_audits_clean_split_refund_and_faults(seed, fault):
    dims = {"postings": 400, "documents": 80}
    if fault is None:
        public, truth, _ = build_settlement_company(seed, dims)
    else:
        public, truth, _ = build_settlement_fault_episode(
            seed, {**dims, "fault": fault})
    report = audit_company(public, truth)
    assert report["status"] == "PASS"
    assert report["issues_audited"] == len(truth["issues"])
    assert report["refund_count"] >= 1


@pytest.mark.parametrize("zone", ["+03:00", "+05:00", "+09:00"])
@pytest.mark.parametrize("currency", ["USD", "EUR"])
@pytest.mark.parametrize("period", ["2026-02", "2026-03", "2026-10"])
@pytest.mark.parametrize("profile", [
    {},
    {"faults": {"fx_rate_or_date": 1, "reporting_period": 1}},
    {"compounds": {"fx_allocation": 1, "duplicate_allocation": 1}},
])
def test_new_v1_variants_are_financially_sound(zone, currency, period, profile):
    config = {"postings": 320, "documents": 40,
              "cutoff_timezone": zone, "foreign_currency": currency,
              "period_month": period, **profile}
    public, truth, provenance = build_company(42, config)
    report = audit_company(public, truth)
    assert report["status"] == "PASS"
    assert report["issues_audited"] == len(truth["issues"])
    assert public["manifest"]["timezone"] == zone
    assert public["manifest"]["period_start"][:7] == period
    assert public["manifest"]["period_end"][:7] == period
    assert public["policy"]["currency_exponents"] == {"KZT": 2, currency: 2}
    assert {rate["source_currency"] for rate in public["tables"]["fx"]} == {currency}
    assert all(datetime.fromisoformat(i["issued_at"]).utcoffset() is not None
               for i in public["tables"]["invoices"])
    assert run_baseline(public, truth, "reconciliation")["score"]["fn"] == 0
    assert (public, truth) == build_company(42, config)[:2]
    assert provenance["config"]["period_month"] == period


@pytest.mark.parametrize("config", [
    {"foreign_currency": "GBP"},
    {"foreign_currency": "BTC"},
    {"cutoff_timezone": "+00:00"},
    {"cutoff_timezone": "UTC"},
    {"period_month": "2026-13"},
    {"period_month": "2026-1"},
    {"period_month": 202603},
])
def test_variant_generator_fails_closed_for_unsupported_parameters(config):
    with pytest.raises(ValueError):
        build_company(19, config)


def test_default_legacy_scenario_remains_unchanged_with_explicit_defaults():
    a = build_company(42, {"postings": 320, "documents": 40})
    b = build_company(42, {"postings": 320, "documents": 40,
                           "foreign_currency": "USD",
                           "cutoff_timezone": "+05:00",
                           "period_month": "2026-02"})
    assert a[0] == b[0] and a[1] == b[1]
    assert audit_company(*a[:2])["status"] == "PASS"


def test_independent_v1_rejects_balanced_but_fabricated_postings():
    public, truth, _ = build_company(2026, {"postings": 320, "documents": 40})
    tampered = copy.deepcopy(public)
    iid = tampered["tables"]["invoices"][0]["invoice_id"]
    rows = [x for x in tampered["tables"]["ledger"]
            if x["invoice_id"] == iid and x["payment_id"] is None]
    next(x for x in rows if x["account"] == "expense")["debit_minor"] += 1
    next(x for x in rows if x["account"] == "payable")["credit_minor"] += 1
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(tampered, truth)


def test_independent_v1_rejects_forged_truth_and_evidence():
    public, truth, _ = build_company(
        2026, {"postings": 320, "documents": 40,
               "compounds": {"fx_allocation": 1}})
    missing = copy.deepcopy(truth)
    missing["issues"][0]["allowed_evidence_sets"] = [["not-public"]]
    with pytest.raises(ValueError, match="evidence"):
        audit_company(public, missing)
    fake_amount = copy.deepcopy(truth)
    fake_amount["issues"][0]["expected_amount_minor"] += 2
    with pytest.raises(ValueError, match="truth"):
        audit_company(public, fake_amount)


def test_independent_v2_rejects_corrupted_refund_while_balanced():
    public, truth, _ = build_settlement_company(
        2026, {"postings": 320, "documents": 40})
    broken = copy.deepcopy(public)
    refund = next(p for p in broken["tables"]["payments"] if p["kind"] == "refund")
    refund["invoice_refs"][0]["amount_minor"] += 1
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(broken, truth)


@pytest.mark.parametrize("tamper", [
    "wrong_remittance_anchor",
    "refund_journal_provenance",
    "repeated_public_row_id",
    "duplicate_foreign_quote",
    "payment_entity",
])
def test_independent_v2_rejects_valid_money_with_corrupted_evidence(tamper):
    public, truth, _ = build_settlement_company(
        2026, {"postings": 320, "documents": 40})
    public = copy.deepcopy(public)
    if tamper == "wrong_remittance_anchor":
        normal = next(p for p in public["tables"]["payments"]
                      if p["kind"] == "payment" and len(p["invoice_refs"]) == 1)
        normal["remittance_invoice_id"] = None
    elif tamper == "refund_journal_provenance":
        refund = next(p for p in public["tables"]["payments"] if p["kind"] == "refund")
        journal = next(row for row in public["tables"]["ledger"]
                       if row["payment_id"] == refund["payment_id"])
        journal["invoice_id"] = public["tables"]["invoices"][0]["invoice_id"]
    elif tamper == "repeated_public_row_id":
        public["tables"]["ledger"][0]["row_id"] = public["tables"]["ledger"][-1]["row_id"]
    elif tamper == "duplicate_foreign_quote":
        public["tables"]["fx"][0]["date"] = public["tables"]["fx"][1]["date"]
    else:
        normal = next(p for p in public["tables"]["payments"]
                      if p["kind"] == "payment" and len(p["invoice_refs"]) == 1)
        normal["entity_id"] = "unauthorized-vendor"
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(public, truth)


def test_independent_v2_rejects_forged_truth_evidence():
    public, truth, _ = build_settlement_fault_episode(
        2026, {"postings": 320, "documents": 40,
               "fault": "duplicate_allocation"})
    forged = copy.deepcopy(truth)
    forged["issues"][0]["allowed_evidence_sets"] = [["nonpublic-invoice"]]
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(public, forged)


def test_independent_v1_detects_policy_tampering():
    public, truth, _ = build_company(
        42, {"postings": 320, "documents": 40,
             "foreign_currency": "EUR", "cutoff_timezone": "+09:00",
             "period_month": "2026-10"})
    assert audit_company(public, truth)["status"] == "PASS"
    corrupt = copy.deepcopy(public)
    corrupt["policy"]["cutoff_timezone"] = "+05:00"
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(corrupt, truth)
    corrupt = copy.deepcopy(public)
    corrupt["policy"]["currency_exponents"] = {"KZT": 2, "JPY": 0}
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(corrupt, truth)
