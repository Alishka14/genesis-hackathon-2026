"""Independent financial acceptance probes using synthetic, generated public facts."""
import copy

import pytest

from ledgergym.company_world import build_company
from ledgergym.independent_audit import audit_company_public
from ledgergym.score import accessible_evidence_ids


def _signature(issue):
    return (issue["type"], tuple(sorted(issue["affected_ids"])),
            issue["expected_amount_minor"], issue["currency"])


CONFIGS = [
    {},
    {"faults": {"duplicate_invoice": 1}},
    {"faults": {"payment_allocation": 1}},
    {"faults": {"fx_rate_or_date": 1}},
    {"faults": {"reporting_period": 1}},
    {"compounds": {"fx_allocation": 1}},
    {"compounds": {"duplicate_allocation": 1}},
    {"faults": {"duplicate_invoice": 1, "payment_allocation": 1,
                "fx_rate_or_date": 1, "reporting_period": 1}},
    {"postings": 2000, "documents": 200,
     "faults": {"duplicate_invoice": 2, "payment_allocation": 2,
                "fx_rate_or_date": 2, "reporting_period": 2},
     "compounds": {"fx_allocation": 1, "duplicate_allocation": 1}},
]


@pytest.mark.parametrize("config", CONFIGS)
def test_independent_public_facts_agree_with_private_truth(config):
    # The oracle imports only Python stdlib, not any generator, baseline or shared validator.
    public, truth, _ = build_company(81, config)
    report = audit_company_public(public)
    actual = sorted(_signature(issue) for issue in truth["issues"])
    assert report["issues"] == actual
    assert report["checked_postings"] == len(public["tables"]["ledger"])
    assert report["checked_documents"] == (len(public["tables"]["payments"]) +
                                           len(public["tables"]["invoices"]))
    addressable = accessible_evidence_ids(public)
    for issue in truth["issues"]:
        key = _signature(issue)
        expected_docs = report["evidence"][key]
        assert expected_docs <= addressable
        assert any(expected_docs <= set(group) <= addressable
                   for group in issue["allowed_evidence_sets"])


@pytest.mark.parametrize("seed", [0, 17, 99])
def test_independent_public_issues_hold_for_different_seeds(seed):
    config = {"faults": {"duplicate_invoice": 1, "payment_allocation": 1,
                         "fx_rate_or_date": 1, "reporting_period": 1},
              "compounds": {"fx_allocation": 1, "duplicate_allocation": 1}}
    public, truth, _ = build_company(seed, config)
    assert audit_company_public(public)["issues"] == sorted(_signature(i) for i in truth["issues"])


def test_independent_audit_does_not_depend_on_private_truth():
    public, _, _ = build_company(81, {})
    report = audit_company_public(public)
    assert report["issues"] == []
    altered = copy.deepcopy(public)
    p = altered["tables"]["payments"][0]
    p["invoice_refs"][0]["amount_minor"] -= 1
    changed = audit_company_public(altered)
    assert len(changed["issues"]) == 1
    assert changed["issues"][0][0] == "payment_allocation"


def test_independent_balance_check_fails_if_postings_do_not_balance():
    public, _, _ = build_company(81, {})
    changed = copy.deepcopy(public)
    next(row for row in changed["tables"]["ledger"] if row["debit_minor"] > 0)["debit_minor"] += 7
    with pytest.raises(ValueError, match="balance"):
        audit_company_public(changed)


def test_independent_audit_stable_after_reordering():
    public, _, _ = build_company(81, {"compounds": {"fx_allocation": 1, "duplicate_allocation": 1}})
    initial = audit_company_public(public)
    changed = copy.deepcopy(public)
    for rows in changed["tables"].values():
        rows.reverse()
    assert audit_company_public(changed) == initial
