"""CAB v1: four causal flip families, reversible documented interventions.

Builds both variants from the same seed and verifies that reversing only
the private intervention log exactly recovers the original clean public data.
No agent sees this private record of changes or the clean/fault label.
"""
from __future__ import annotations

import copy
import json

from .baselines import run_baseline
from .company_checks import validate_company
from .company_world import build_company


FAULTS = ("duplicate_invoice", "payment_allocation",
          "fx_rate_or_date", "reporting_period")


def _target(public, change):
    table = change["table"]
    if table == "invoices.line_items":
        records = [
            line for invoice in public["tables"]["invoices"]
            for line in invoice["line_items"]
        ]
        id_field = "line_id"
    elif table == "ledger":
        records = public["tables"]["ledger"]
        id_field = "row_id"
    elif table == "payments":
        records = public["tables"]["payments"]
        id_field = "payment_id"
    else:
        raise ValueError("unrecognised private intervention table")
    matching = [row for row in records if row[id_field] == change["id"]]
    if len(matching) != 1:
        raise ValueError("non-unique intervention target")
    return matching[0]


def audit_v1_causal_pair(seed, fault):
    if type(seed) is not int or fault not in FAULTS:
        raise ValueError("invalid CAB seed or fault family")
    size = {"postings": 200, "documents": 20}
    clean, clean_truth, _ = build_company(seed, size)
    altered, altered_truth, provenance = build_company(
        seed, {**size, "faults": {fault: 1}})
    validate_company(clean, clean_truth)
    validate_company(altered, altered_truth)
    if clean_truth != {"issues": []} or len(altered_truth["issues"]) != 1:
        raise ValueError("invalid clean/fault labels")
    if altered_truth["issues"][0]["type"] != fault:
        raise ValueError("fault type mismatch")
    if clean["manifest"] != altered["manifest"] or clean["policy"] != altered["policy"]:
        raise ValueError("variants do not share the financial contract")

    changes = provenance.get("interventions")
    if not isinstance(changes, list) or not changes:
        raise ValueError("causal pair has no documented intervention")
    reconstructed = copy.deepcopy(altered)
    for change in reversed(changes):
        target = _target(reconstructed, change)
        field = change["field"]
        if target[field] != change["after"]:
            raise ValueError("intervention history disagrees with observed state")
        target[field] = copy.deepcopy(change["before"])
    if reconstructed != clean:
        raise ValueError("reversing causal changes did not restore clean episode")

    before = run_baseline(clean, clean_truth, "reconciliation")["score"]
    after = run_baseline(altered, altered_truth, "reconciliation")["score"]
    if (before["fp"] != 0 or before["fn"] != 0
            or after["tp"] != 1 or after["fp"] != 0 or after["fn"] != 0):
        raise ValueError("baseline missed a validated causal flip")
    return {
        "fault_family": fault,
        "restored_clean_exactly": True,
        "clean_false_positives": before["fp"],
        "fault_true_positives": after["tp"],
        "public_contract_unchanged": True,
        "private_truth_exported": False,
    }


def verify_v1_causal_catalog(*, seeds=(7, 2026)):
    cases = []
    for seed in seeds:
        for fault in FAULTS:
            cases.append(audit_v1_causal_pair(seed, fault))
    return {
        "kind": "trusted_cab_v1_four_fault_causal_flips",
        "pairs": len(cases),
        "families": {family: sum(c["fault_family"] == family for c in cases)
                     for family in FAULTS},
        "reversible_pairs": sum(c["restored_clean_exactly"] for c in cases),
        "private_truth_exported": False,
        "contest_certified": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify_v1_causal_catalog(), sort_keys=True))
