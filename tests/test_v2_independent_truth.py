"""Independent v2 truth cross-check that never imports the fault inspector.

The test oracle re-derives document-level mistakes directly from tables;
this guards against both generator and scorer sharing one mistaken helper.
"""
from collections import defaultdict

import pytest

from ledgergym.company_world_v2 import build_settlement_company
from ledgergym.settlement_faults_v2 import build_settlement_fault_episode


def independent_signatures(public):
    bills = public["tables"]["invoices"]
    by_id = {inv["invoice_id"]: inv for inv in bills}
    groups = defaultdict(list)
    for invoice in bills:
        distinct = {item["service_ref"] for item in invoice["line_items"]}
        assert len(distinct) == 1
        groups[(invoice["entity_id"], next(iter(distinct)))].append(invoice)
    discovered = set()
    for group in groups.values():
        if len(group) == 2:
            a, b = group
            assert a["currency"] == b["currency"]
            assert a["total_minor"] == b["total_minor"]
            discovered.add(("duplicate_invoice",
                            tuple(sorted([a["invoice_id"], b["invoice_id"]])),
                            a["total_minor"], a["currency"]))
        else:
            assert len(group) == 1
    for payment in public["tables"]["payments"]:
        basis = payment.get("allocation_basis")
        if basis is None:
            continue
        expected = {x["invoice_id"]: x["amount_minor"] for x in basis}
        observed = {x["invoice_id"]: x["amount_minor"] for x in payment["invoice_refs"]}
        assert expected.keys() == observed.keys()
        assert sum(expected.values()) == payment["amount_minor"]
        for invoice_id in expected:
            difference = expected[invoice_id] - observed[invoice_id]
            if difference:
                assert difference > 0
                assert payment["currency"] == by_id[invoice_id]["currency"] == "KZT"
                discovered.add(("payment_allocation",
                                tuple(sorted([payment["payment_id"], invoice_id])),
                                difference, "KZT"))
    return discovered


@pytest.mark.parametrize("mode", ["duplicate_invoice", "payment_allocation", "duplicate_allocation"])
@pytest.mark.parametrize("seed", [7, 81, 2026, 9999])
def test_public_only_independent_truth_matches_private_labels(mode, seed):
    size = {"postings": 400, "documents": 80}
    clean, _, _ = build_settlement_company(seed, size)
    faulty, truth, _ = build_settlement_fault_episode(seed, {**size, "fault": mode})
    assert independent_signatures(clean) == set()
    expected = independent_signatures(faulty)
    official = {
        (issue["type"], tuple(sorted(issue["affected_ids"])),
         issue["expected_amount_minor"], issue["currency"])
        for issue in truth["issues"]
    }
    assert expected == official
    assert len(expected) == (2 if mode == "duplicate_allocation" else 1)
