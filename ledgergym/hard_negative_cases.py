"""Reproducible clean-but-suspicious settlement cases for offline QA.

These are *internal* finance fixtures, not complete six-file RL episodes.
No private truth is included in the simulated financial input. The helper
never claims compatibility with the original company's one-remittance policy.
"""
from random import Random


KINDS = (
    "equal_values_distinct_services",
    "split_payment",
    "multiple_partial_payments",
    "partial_refund",
    "split_with_refund",
    "parallel_currencies",
)


def make_hard_negative_case(seed: int, kind: str):
    """Generate deterministic documentary movements with no actual violation."""
    if type(seed) is not int or kind not in KINDS:
        raise ValueError("unknown hard-negative configuration")
    rng = Random(f"ledgergym-negative-v1:{seed}")
    def identifier():
        return f"r-{rng.getrandbits(96):024x}"
    inv_ids, doc_ids, payment_ids = [identifier() for _ in range(2)], [identifier() for _ in range(2)], [identifier() for _ in range(2)]
    entity_id = identifier()
    service_ids = [identifier() for _ in range(2)]
    currencies = ["USD", "KZT"] if kind == "parallel_currencies" else ["KZT", "KZT"]
    invoices = [
        {
            "invoice_id": inv_ids[i], "doc_id": doc_ids[i],
            "entity_id": entity_id, "currency": currencies[i],
            "issued_at": "2026-02-01T09:00:00+05:00",
            "total_minor": 10000,
            "line_items": [{"service_ref": service_ids[i], "amount_minor": 10000}],
        }
        for i in range(2)
    ]

    def payment(index, amount, allocations, when="2026-02-03T12:00:00+05:00"):
        return {
            "payment_id": payment_ids[index], "entity_id": entity_id,
            "currency": currencies[allocations[0][0]], "timestamp": when,
            "amount_minor": amount,
            "invoice_refs": [
                {"invoice_id": inv_ids[inv_idx], "amount_minor": share}
                for inv_idx, share in allocations
            ],
        }

    refunds = []
    if kind in ("equal_values_distinct_services", "parallel_currencies"):
        payments = [payment(0, 10000, [(0, 10000)]),
                    payment(1, 10000, [(1, 10000)])]
    elif kind == "split_payment":
        payments = [payment(0, 15000, [(0, 9000), (1, 6000)])]
    elif kind == "multiple_partial_payments":
        payments = [payment(0, 3000, [(0, 3000)]),
                    payment(1, 4000, [(0, 4000)], when="2026-02-03T13:00:00+05:00")]
    elif kind == "partial_refund":
        payments = [payment(0, 10000, [(0, 10000)]),
                    payment(1, 10000, [(1, 10000)])]
        refunds = [{
            "refund_id": identifier(), "kind": "refund", "original_payment_id": payment_ids[0],
            "entity_id": entity_id, "currency": "KZT",
            "timestamp": "2026-02-04T12:00:00+05:00",
            "amount_minor": 3000,
            "invoice_refs": [{"invoice_id": inv_ids[0], "amount_minor": 3000}],
        }]
    elif kind == "split_with_refund":
        payments = [payment(0, 17000, [(0, 8000), (1, 9000)])]
        refunds = [{
            "refund_id": identifier(), "kind": "refund", "original_payment_id": payment_ids[0],
            "entity_id": entity_id, "currency": "KZT",
            "timestamp": "2026-02-04T12:00:00+05:00", "amount_minor": 6000,
            "invoice_refs": [
                {"invoice_id": inv_ids[0], "amount_minor": 2000},
                {"invoice_id": inv_ids[1], "amount_minor": 4000},
            ],
        }]
    else:
        raise ValueError("unknown case")

    return {"invoices": invoices, "payments": payments, "refunds": refunds}
