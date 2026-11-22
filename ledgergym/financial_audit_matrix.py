"""Reproducible financial audit matrix behind docs/FINANCIAL_AUDIT_REPORT.md.

7 scenario configurations x a fixed seed range (default 0..99 -> 700 worlds).
Per world: global double-entry balance (and empty truth for clean worlds).
Per labelled issue: the expected amount is recomputed from PUBLIC tables only.

Independence: this module does not import company_checks.inspect_company, the
generator's Decimal conversion or score.py. It uses its own Fraction-based
ROUND_HALF_EVEN and re-reads the published policy semantics. It still shares
the published accounting rules (what counts as "correct"), so it is a
cross-implementation check, not an external professional audit.

    python -m ledgergym.financial_audit_matrix [--seeds 100] [--varied] [--report out.json]
Exit code 0 only if every check passes.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import sys

from .company_world import build_company

CONFIGS = {
    "clean": {},
    "duplicate_invoice": {"faults": {"duplicate_invoice": 1}},
    "payment_allocation": {"faults": {"payment_allocation": 1}},
    "fx_rate_or_date": {"faults": {"fx_rate_or_date": 1}},
    "reporting_period": {"faults": {"reporting_period": 1}},
    "fx_allocation": {"compounds": {"fx_allocation": 1}},
    "duplicate_allocation": {"compounds": {"duplicate_allocation": 1}},
}

# Opt-in generator options (see company_world.OPTIONS) exercised by --varied.
VARIED = {"fault_parameters": "varied", "timestamp_offsets": "mixed", "evidence_alternatives": True}


def round_half_even(amount, rate):
    value = amount * Fraction(rate)
    whole, rest = divmod(value.numerator, value.denominator)
    return whole + int(2 * rest > value.denominator or (2 * rest == value.denominator and whole % 2))


def _zone(policy):
    text = policy["cutoff_timezone"]
    sign = -1 if text[0] == "-" else 1
    return timezone(sign * timedelta(hours=int(text[1:3]), minutes=int(text[4:6])))


def check_world(public, truth):
    """Return a list of (check_name, ok, detail) derived from public facts."""
    tables, zone = public["tables"], _zone(public["policy"])
    ledger = tables["ledger"]
    invoices = {i["invoice_id"]: i for i in tables["invoices"]}
    payments = {p["payment_id"]: p for p in tables["payments"]}
    fx_by_date = {r["date"]: r for r in tables["fx"]}
    fx_by_id = {r["rate_id"]: r for r in tables["fx"]}

    def local(stamp):
        return datetime.fromisoformat(stamp).astimezone(zone)

    def correct_rate(currency, stamp):
        if currency == public["manifest"]["base_currency"]:
            return "1"
        return fx_by_date[local(stamp).date().isoformat()]["rate"]

    results = []
    balanced = sum(r["debit_minor"] for r in ledger) == sum(r["credit_minor"] for r in ledger)
    results.append(("balance", balanced, None))
    for issue in truth["issues"]:
        kind, expected, got = issue["type"], issue["expected_amount_minor"], None
        try:
            if kind == "payment_allocation":
                p = next(payments[x] for x in issue["affected_ids"] if x in payments)
                allocated = sum(r["amount_minor"] for r in p["invoice_refs"]
                                if r["invoice_id"] == p["remittance_invoice_id"])
                got = round_half_even(p["amount_minor"] - allocated, correct_rate(p["currency"], p["timestamp"]))
            elif kind == "fx_rate_or_date":
                p = next(payments[x] for x in issue["affected_ids"] if x in payments)
                rows = [r for r in ledger if r["payment_id"] == p["payment_id"]]
                recorded = next(r["debit_minor"] for r in rows if r["account"] == "payable")
                used = fx_by_id[rows[0]["rate_id"]]
                consistent = (recorded == round_half_even(p["amount_minor"], used["rate"])
                              and used["date"] != local(p["timestamp"]).date().isoformat())
                if consistent:
                    got = abs(round_half_even(p["amount_minor"], correct_rate(p["currency"], p["timestamp"])) - recorded)
            elif kind == "reporting_period":
                inv = invoices[issue["affected_ids"][0]]
                rows = [r for r in ledger if r["invoice_id"] == inv["invoice_id"] and r["payment_id"] is None]
                month = local(inv["issued_at"]).strftime("%Y-%m")
                if rows and all(r["reporting_period"] != month for r in rows):
                    got = round_half_even(inv["total_minor"], correct_rate(inv["currency"], inv["issued_at"]))
            elif kind == "duplicate_invoice":
                a, b = (invoices[x] for x in issue["affected_ids"])
                same_service = ({l["service_ref"] for l in a["line_items"]}
                                == {l["service_ref"] for l in b["line_items"]})
                if (same_service and a["entity_id"] == b["entity_id"] and a["total_minor"] == b["total_minor"]
                        and a["currency"] == b["currency"] == issue["currency"]):
                    got = b["total_minor"]
        except (KeyError, StopIteration, IndexError, ValueError):
            got = None
        results.append((kind, got == expected, {"expected": expected, "recomputed": got}))
    return results


def run_matrix(seeds=range(100), configs=CONFIGS, options=None):
    checks, failures, worlds = Counter(), [], 0
    for name, config in configs.items():
        for seed in seeds:
            public, truth, _ = build_company(seed, {**config, **(options or {})})
            worlds += 1
            for check, ok, detail in check_world(public, truth):
                if name == "clean" and check == "balance":
                    ok = ok and truth["issues"] == []
                checks[check] += 1
                if not ok:
                    failures.append({"config": name, "seed": seed, "check": check, "detail": detail})
    return {"method": "public_tables_fraction_recompute_v1", "configs": list(configs), "options": options or {},
            "seeds": [min(seeds), max(seeds)] if len(seeds) else [], "worlds": worlds,
            "checks": dict(checks), "total_checks": sum(checks.values()),
            "failed": len(failures), "failures": failures[:20], "success": not failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reproducible LedgerGym financial audit matrix.")
    parser.add_argument("--seeds", type=int, default=100, help="seeds 0..N-1 per configuration")
    parser.add_argument("--varied", action="store_true", help="enable all opt-in generator variation options")
    parser.add_argument("--report", type=Path, help="optional JSON report path (must not exist)")
    args = parser.parse_args(argv)
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    report = run_matrix(range(args.seeds), options=VARIED if args.varied else None)
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
