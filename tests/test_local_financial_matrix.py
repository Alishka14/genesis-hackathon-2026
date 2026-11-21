"""Local 20-case synthetic financial acceptance battery.

LG-F01..LG-F20 are INTERNAL coverage labels. They are NOT the organizer's
unpublished closed D01..D20 cases. No hidden judge benchmark is implied.
"""
import copy
import json
from collections import Counter

import pytest

from ledgergym.company_world import build_company
from ledgergym.independent_audit import audit_company_public
from ledgergym.score import accessible_evidence_ids


def _case(identifier, seed, postings=400, documents=80, faults=None, compounds=None):
    config = {"postings": postings, "documents": documents}
    if faults:
        config["faults"] = faults
    if compounds:
        config["compounds"] = compounds
    return pytest.param(seed, config, id=identifier)


CASES = [
    _case("LG-F01-clean-min", 81, 200, 20),
    _case("LG-F02-clean-standard", 17),
    _case("LG-F03-clean-max", 91, 2000, 200),
    _case("LG-F04-duplicate-one", 81, 200, 20, {"duplicate_invoice": 1}),
    _case("LG-F05-duplicate-two", 99, faults={"duplicate_invoice": 2}),
    _case("LG-F06-allocation-one", 81, 200, 20, {"payment_allocation": 1}),
    _case("LG-F07-allocation-two", 99, faults={"payment_allocation": 2}),
    _case("LG-F08-fx-one", 81, 200, 20, {"fx_rate_or_date": 1}),
    _case("LG-F09-fx-two", 99, faults={"fx_rate_or_date": 2}),
    _case("LG-F10-cutoff-one", 81, 200, 20, {"reporting_period": 1}),
    _case("LG-F11-cutoff-two", 99, faults={"reporting_period": 2}),
    _case("LG-F12-four-independent", 81, faults={
        "duplicate_invoice": 1, "payment_allocation": 1,
        "fx_rate_or_date": 1, "reporting_period": 1}),
    _case("LG-F13-duplicate-and-allocation", 17, faults={
        "duplicate_invoice": 1, "payment_allocation": 1}),
    _case("LG-F14-fx-and-cutoff", 17, faults={
        "fx_rate_or_date": 1, "reporting_period": 1}),
    _case("LG-F15-fx-allocation-compound", 81, compounds={"fx_allocation": 1}),
    _case("LG-F16-duplicate-allocation-compound", 81, compounds={"duplicate_allocation": 1}),
    _case("LG-F17-both-compounds", 17, compounds={
        "fx_allocation": 1, "duplicate_allocation": 1}),
    _case("LG-F18-four-plus-compounds", 17, faults={
        "duplicate_invoice": 1, "payment_allocation": 1,
        "fx_rate_or_date": 1, "reporting_period": 1},
          compounds={"fx_allocation": 1, "duplicate_allocation": 1}),
    _case("LG-F19-max-12-issues", 81, 2000, 200, faults={
        "duplicate_invoice": 2, "payment_allocation": 2,
        "fx_rate_or_date": 2, "reporting_period": 2},
          compounds={"fx_allocation": 1, "duplicate_allocation": 1}),
    _case("LG-F20-clean-equal-valued-obligations", 12345),
]


def _expected_counts(config):
    c = Counter(config.get("faults", {}))
    compounds = config.get("compounds", {})
    for name, number in compounds.items():
        if name == "fx_allocation":
            c.update({"fx_rate_or_date": number, "payment_allocation": number})
        elif name == "duplicate_allocation":
            c.update({"duplicate_invoice": number, "payment_allocation": number})
        else:
            raise AssertionError("unrecognized compound in verification matrix")
    return +c


def _signature(issue):
    return (issue["type"], tuple(sorted(issue["affected_ids"])),
            issue["expected_amount_minor"], issue["currency"])


def _restore_from_provenance(public, provenance):
    """Reverse the recorded *mutations* rather than trusting truth labels."""
    restored = copy.deepcopy(public)
    for change in reversed(provenance["interventions"]):
        if change["table"] == "invoices.line_items":
            records = [line for invoice in restored["tables"]["invoices"]
                       for line in invoice["line_items"]]
            key = "line_id"
        else:
            records = restored["tables"][change["table"]]
            key = {"ledger": "row_id", "payments": "payment_id"}[change["table"]]
        matching = [record for record in records if record[key] == change["id"]]
        assert len(matching) == 1
        target = matching[0]
        assert target[change["field"]] == change["after"]
        target[change["field"]] = change["before"]
    return restored


@pytest.mark.parametrize("seed,config", CASES)
def test_lg_local_financial_matrix(seed, config):
    public, truth, provenance = build_company(seed, config)
    tables = public["tables"]
    assert len(tables["ledger"]) == config["postings"]
    assert len(tables["payments"]) + len(tables["invoices"]) == config["documents"]
    assert sum(row["debit_minor"] - row["credit_minor"]
               for row in tables["ledger"]) == 0
    assert sum(_expected_counts(config).values()) == len(truth["issues"])
    assert Counter(issue["type"] for issue in truth["issues"]) == _expected_counts(config)
    assert len(truth["issues"]) <= 12

    # This is a fresh public-only implementation (Fraction), not the generator
    # and not a reflection of its private expected labels.
    independent = audit_company_public(public)
    assert independent["issues"] == sorted(_signature(i) for i in truth["issues"])
    addressable = accessible_evidence_ids(public)
    for issue in truth["issues"]:
        signature = _signature(issue)
        required = independent["evidence"][signature]
        evidence_sets = issue["allowed_evidence_sets"]
        assert evidence_sets
        assert any(required <= set(group) <= addressable and
                   0 < len(group) <= 10 for group in evidence_sets)

    # A separate private provenance reverse-check catches incidental changes
    # not justified by planned fault injections.
    restored = _restore_from_provenance(public, provenance)
    clean, clean_truth, _ = build_company(seed, {"postings": config["postings"],
                                                  "documents": config["documents"]})
    assert clean_truth["issues"] == []
    assert restored == clean
    assert not audit_company_public(restored)["issues"]
    assert len(provenance["interventions"]) == 0 if not truth["issues"] else len(provenance["interventions"]) > 0
    assert json.dumps(public, ensure_ascii=False, sort_keys=True) == json.dumps(
        build_company(seed, config)[0], ensure_ascii=False, sort_keys=True)


def test_local_matrix_has_exactly_twenty_distinct_cases():
    assert len(CASES) == 20
    assert len({param.id for param in CASES}) == 20


def test_the_two_compounds_have_private_two_issue_groups():
    config = {"compounds": {"fx_allocation": 1, "duplicate_allocation": 1}}
    _, truth, provenance = build_company(81, config)
    groups = provenance["compound_groups"]
    assert len(groups) == 2
    issues = {i["issue_id"]: i for i in truth["issues"]}
    assert set(issues) == {issue_id for group in groups for issue_id in group["issue_ids"]}
    for group in groups:
        assert len(group["issue_ids"]) == 2
        assert len(set(group["issue_ids"])) == 2
        kinds = {issues[issue_id]["type"] for issue_id in group["issue_ids"]}
        assert kinds == ({"fx_rate_or_date", "payment_allocation"} if group["kind"] == "fx_allocation"
                         else {"duplicate_invoice", "payment_allocation"})
        assert group["payment_id"] and isinstance(group["payment_id"], str)


def test_independent_oracle_not_fooled_by_ref_change_without_truth_update():
    public, _, _ = build_company(81, {})
    reference = audit_company_public(public)
    assert reference["issues"] == []
    changed = copy.deepcopy(public)
    payment = changed["tables"]["payments"][0]
    payment["invoice_refs"][0]["amount_minor"] -= 1
    affected = audit_company_public(changed)["issues"]
    assert len(affected) == 1 and affected[0][0] == "payment_allocation"
