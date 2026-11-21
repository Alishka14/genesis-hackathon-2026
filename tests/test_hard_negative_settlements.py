"""Positive and negative tests for the standalone clean settlement fixtures."""
import copy
from collections import defaultdict

import pytest

from ledgergym.hard_negative_cases import KINDS, make_hard_negative_case
from ledgergym.refund_settlement import apply_refunds
from ledgergym.score import evaluate
from ledgergym.company_world import build_company
from ledgergym.independent_audit import audit_company_public


EXPECTED_NET = {
    "equal_values_distinct_services": (10000, 10000),
    "split_payment": (9000, 6000),
    "multiple_partial_payments": (7000, 0),
    "partial_refund": (7000, 10000),
    "split_with_refund": (6000, 5000),
    "parallel_currencies": (10000, 10000),
}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("seed", [3, 81, 999])
def test_clean_suspicious_money_is_conserved(kind, seed):
    case = make_hard_negative_case(seed, kind)
    assert case == make_hard_negative_case(seed, kind)
    original = copy.deepcopy(case)
    result = apply_refunds(case["invoices"], case["payments"], case["refunds"])
    assert case == original
    invoice_ids = [x["invoice_id"] for x in case["invoices"]]
    assert tuple(result["invoice_balances"][iid]["paid_minor"] for iid in invoice_ids) == EXPECTED_NET[kind]
    assert all(p["status"] == "ALLOCATED" and p["unallocated_minor"] == 0
               for p in result["payments"].values())
    assert all(r["status"] == "APPLIED" for r in result["refunds"].values())

    # Compare independently calculated cash flow per currency with the
    # actual paid balances in each currency, not cross-currency sum.
    by_currency = defaultdict(int)
    for p in case["payments"]:
        by_currency[p["currency"]] += p["amount_minor"]
    for refund in case["refunds"]:
        by_currency[refund["currency"]] -= refund["amount_minor"]
    balances_by_currency = defaultdict(int)
    for invoice in case["invoices"]:
        state = result["invoice_balances"][invoice["invoice_id"]]
        assert 0 <= state["paid_minor"] <= invoice["total_minor"]
        assert state["paid_minor"] + state["outstanding_minor"] == invoice["total_minor"]
        balances_by_currency[state["currency"]] += state["paid_minor"]
    assert dict(by_currency) == dict(balances_by_currency)


@pytest.mark.parametrize("kind", KINDS)
def test_equal_invoice_amount_is_not_evidence_of_duplicate(kind):
    case = make_hard_negative_case(7, kind)
    a, b = case["invoices"]
    assert a["total_minor"] == b["total_minor"]
    assert a["entity_id"] == b["entity_id"]
    assert a["line_items"][0]["service_ref"] != b["line_items"][0]["service_ref"]
    fake = {
        "type": "duplicate_invoice", "affected_ids": [a["invoice_id"], b["invoice_id"]],
        "claimed_amount_minor": a["total_minor"], "currency": a["currency"],
        "evidence_ids": [a["doc_id"], b["doc_id"]], "explanation": "Equal amounts: unjustified"
    }
    ids = {i["invoice_id"] for i in case["invoices"]}
    ids.update(i["doc_id"] for i in case["invoices"])
    result = evaluate([], [fake], ids, 0)
    assert (result["tp"], result["fp"], result["fn"], result["f1"], result["reward"]) == (0, 1, 0, 0., -1.)


def test_refunds_refuse_double_claims_across_documents():
    case = make_hard_negative_case(11, "partial_refund")
    refund = copy.deepcopy(case["refunds"][0])
    refund["refund_id"] += "-second"
    refund["amount_minor"] = 8000
    refund["invoice_refs"][0]["amount_minor"] = 8000
    with pytest.raises(ValueError, match="exceed"):
        apply_refunds(case["invoices"], case["payments"], case["refunds"] + [refund])


@pytest.mark.parametrize("edit,expected", [
    ({"amount_minor": 0}, "amount"),
    ({"amount_minor": -10}, "amount"),
    ({"amount_minor": True}, "amount"),
    ({"amount_minor": 1.0}, "amount"),
    ({"currency": "USD"}, "currency"),
    ({"currency": "kzt"}, "currency"),
    ({"entity_id": "unrelated-supplier"}, "entity"),
    ({"original_payment_id": "unknown"}, "original"),
    ({"timestamp": "2026-02-02T12:00:00+05:00"}, "after"),
    ({"kind": "reversal"}, "movement"),
])
def test_invalid_refund_document_is_rejected(edit, expected):
    case = make_hard_negative_case(1, "partial_refund")
    case["refunds"][0].update(edit)
    with pytest.raises(ValueError, match=expected):
        apply_refunds(case["invoices"], case["payments"], case["refunds"])


def test_incorrect_refund_invoice_reference_is_rejected():
    case = make_hard_negative_case(81, "partial_refund")
    case["refunds"][0]["invoice_refs"][0]["invoice_id"] = case["invoices"][1]["invoice_id"]
    with pytest.raises(ValueError, match="not part"):
        apply_refunds(case["invoices"], case["payments"], case["refunds"])


def test_invalid_refund_amount_not_matching_references_is_rejected():
    case = make_hard_negative_case(81, "partial_refund")
    case["refunds"][0]["invoice_refs"][0]["amount_minor"] = 2000
    with pytest.raises(ValueError, match="does not equal"):
        apply_refunds(case["invoices"], case["payments"], case["refunds"])


def test_duplicate_refund_id_is_rejected():
    case = make_hard_negative_case(81, "partial_refund")
    with pytest.raises(ValueError, match="duplicate refund"):
        apply_refunds(case["invoices"], case["payments"], case["refunds"] * 2)


def test_repeated_invoice_reference_is_rejected():
    case = make_hard_negative_case(81, "partial_refund")
    original = case["refunds"][0]
    original["invoice_refs"].append(copy.deepcopy(original["invoice_refs"][0]))
    original["amount_minor"] *= 2
    with pytest.raises(ValueError, match="repeated invoice"):
        apply_refunds(case["invoices"], case["payments"], case["refunds"])


def test_out_of_scope_interleaved_refund_is_not_silently_processed():
    case = make_hard_negative_case(81, "multiple_partial_payments")
    refund = {
        "refund_id": "new-01", "kind": "refund",
        "original_payment_id": case["payments"][0]["payment_id"],
        "entity_id": case["invoices"][0]["entity_id"], "currency": "KZT",
        "timestamp": "2026-02-03T12:30:00+05:00",
        "amount_minor": 1000,
        "invoice_refs": [{"invoice_id": case["invoices"][0]["invoice_id"], "amount_minor": 1000}],
    }
    with pytest.raises(ValueError, match="after ordinary transfers"):
        apply_refunds(case["invoices"], case["payments"], [refund])


def test_refund_requires_unambiguous_original_payment():
    case = make_hard_negative_case(81, "partial_refund")
    case["payments"][0]["invoice_refs"] = []
    with pytest.raises(ValueError, match="fully allocated"):
        apply_refunds(case["invoices"], case["payments"], case["refunds"])


@pytest.mark.parametrize("kind", KINDS)
def test_order_invariance_and_id_identity(kind):
    case = make_hard_negative_case(81, kind)
    result = apply_refunds(case["invoices"], case["payments"], case["refunds"])
    changed = copy.deepcopy(case)
    for key in changed:
        changed[key].reverse()
    assert apply_refunds(changed["invoices"], changed["payments"], changed["refunds"]) == result


def test_production_clean_company_has_identical_values_but_distinct_service_refs():
    public, truth, _ = build_company(81, {"postings": 400, "documents": 80})
    first, second = public["tables"]["invoices"][:2]
    # company-world is shuffled: locate a genuine pair by vendor, amount
    # and currency while their service ids intentionally remain distinct.
    invoices = public["tables"]["invoices"]
    pairs = [
        (a, b) for idx, a in enumerate(invoices) for b in invoices[idx + 1:]
        if a["entity_id"] == b["entity_id"] and a["currency"] == b["currency"]
        and a["total_minor"] == b["total_minor"]
        and a["line_items"][0]["service_ref"] != b["line_items"][0]["service_ref"]
    ]
    assert pairs and truth["issues"] == []
    assert audit_company_public(public)["issues"] == []
