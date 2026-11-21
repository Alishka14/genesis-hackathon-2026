"""Evaluator-only independent v1 financial audit (not an agent-side tool).

Deliberately does not import company_world, company_checks, baselines or score.
Re-derives exact posted amounts, incident signatures and minimum accessible
evidence from public source documents with Decimal and separate journal walks.
This detects shared modeling mistakes better than evaluating the baseline
against the generator's own scorer, but is still a *second code implementation*
of the same agreed synthetic accounting policy, NOT an external accountant.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import re


def _need(ok, why):
    if not ok:
        raise ValueError("independent audit: " + why)


def _amount(value):
    return type(value) is int and value > 0


def _converted(amount, rate):
    _need(type(amount) is int and isinstance(rate, str), "invalid money/FX")
    return int((Decimal(amount) * Decimal(rate)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _signature(x, amount_key):
    return (x["type"], tuple(sorted(x["affected_ids"])), x[amount_key], x["currency"])


def _issue(kind, affected, amount, currency, evidence):
    return {"type": kind, "affected_ids": sorted(affected),
            "claimed_amount_minor": amount, "currency": currency,
            "evidence_ids": sorted(set(evidence))}


def verify_truth_evidence(derived, truth, public):
    """Compare independently derived discrepancies to exact evaluator labels."""
    _need(isinstance(truth, dict) and set(truth) == {"issues"}
          and isinstance(truth["issues"], list), "malformed private truth")
    _need(len(derived) == len(truth["issues"]) <= 12, "issue cardinality differs")
    public_ids = set()
    for table, field in (("ledger", "row_id"), ("invoices", "invoice_id"),
                         ("payments", "payment_id"), ("fx", "rate_id")):
        for row in public["tables"][table]:
            public_ids.add(row[field])
            if table in ("invoices", "payments"):
                public_ids.add(row["doc_id"])
    signatures = {_signature(f, "claimed_amount_minor"): set(f["evidence_ids"]) for f in derived}
    _need(len(signatures) == len(derived), "ambiguous independent issue")
    seen = set()
    for issue in truth["issues"]:
        _need(isinstance(issue, dict) and set(issue) == {
              "issue_id", "type", "affected_ids", "expected_amount_minor",
              "currency", "allowed_evidence_sets"}, "unexpected private issue fields")
        key = _signature(issue, "expected_amount_minor")
        _need(key in signatures and key not in seen, "truth not supported by public accounting")
        seen.add(key)
        _need(type(issue["expected_amount_minor"]) is int and
              isinstance(issue["issue_id"], str) and issue["issue_id"] not in public_ids,
              "private truth money or identifier invalid")
        _need(len(set(issue["affected_ids"])) == len(issue["affected_ids"])
              and set(issue["affected_ids"]) <= public_ids, "affected ID not publicly accessible")
        _need(isinstance(issue["allowed_evidence_sets"], list)
              and issue["allowed_evidence_sets"], "missing allowed evidence")
        for group in issue["allowed_evidence_sets"]:
            _need(isinstance(group, list) and len(group) <= 10
                  and len(group) == len(set(group))
                  and signatures[key] <= set(group) <= public_ids,
                  "evidence insufficient, inaccessible or over limit")
    return len(seen)


def audit_v1(public, truth):
    """Independent amount/period/FX/source/evidence check for supported v1."""
    _need(isinstance(public, dict) and isinstance(public.get("tables"), dict), "bad public episode")
    manifest, policy, t = public["manifest"], public["policy"], public["tables"]
    _need(manifest["schema_version"] == "0.3-company"
          and manifest["base_currency"] == "KZT", "unknown model")
    _need(set(t) == {"invoices", "payments", "ledger", "fx"}, "missing table")
    _need(manifest["counts"] == {key: len(rows) for key, rows in t.items()},
          "manifest count differs")
    _need(policy["accounting_model"] == "accrual_company_v1"
          and policy["rounding"] == "ROUND_HALF_EVEN"
          and manifest["rounding"] == "ROUND_HALF_EVEN", "incompatible accounting policy")
    zone_name = policy["cutoff_timezone"]
    _need(zone_name == manifest["timezone"] and
          zone_name in ("+03:00", "+05:00", "+09:00"), "unsupported policy zone")
    foreign = next((code for code in ("USD", "EUR")
                    if policy["currency_exponents"] == {"KZT": 2, code: 2}), None)
    _need(foreign is not None, "unsupported foreign currency")
    zone = timezone(timedelta(hours=int(zone_name[1:3])))
    def moment(stamp):
        point = datetime.fromisoformat(stamp)
        _need(point.tzinfo is not None and point.utcoffset() is not None,
              "timestamp without offset")
        return point.astimezone(zone)
    beginning = moment(manifest["period_start"])
    ending = moment(manifest["period_end"])
    _need(beginning <= ending and beginning.strftime("%Y-%m") == ending.strftime("%Y-%m"),
          "invalid company period")

    all_ids = []
    invoices = {}
    payments = {}
    fx = {}
    fx_by_id = {}
    for table, field in (("invoices", "invoice_id"), ("payments", "payment_id"),
                         ("ledger", "row_id"), ("fx", "rate_id")):
        for row in t[table]:
            all_ids.append(row[field])
            if table in ("invoices", "payments"):
                all_ids.append(row["doc_id"])
    _need(all(isinstance(x, str) and x for x in all_ids)
          and len(all_ids) == len(set(all_ids)), "duplicate public identifier")
    for row in t["invoices"]:
        invoices[row["invoice_id"]] = row
    for row in t["payments"]:
        payments[row["payment_id"]] = row
    for row in t["fx"]:
        _need(row["source_currency"] == foreign and
              row["target_currency"] == "KZT" and
              isinstance(row["rate"], str) and Decimal(row["rate"]) > 0,
              "wrong FX pair or rate")
        _need(row["date"] not in fx, "duplicate FX local date")
        fx[row["date"]] = row
        fx_by_id[row["rate_id"]] = row

    def quote(currency, stamp):
        if currency == "KZT":
            return "1", None
        _need(currency == foreign, "unrecognized invoice currency")
        row = fx.get(moment(stamp).date().isoformat())
        _need(row is not None, "no FX quote on local business date")
        return row["rate"], row["rate_id"]

    journal_invoice, journal_payment, opening = defaultdict(list), defaultdict(list), []
    net = 0
    for row in t["ledger"]:
        debit, credit = row["debit_minor"], row["credit_minor"]
        _need(type(debit) is type(credit) is int and debit >= 0 and credit >= 0
              and ((debit > 0) != (credit > 0)) and row["currency"] == "KZT",
              "invalid single-sided journal entry")
        _need(beginning <= moment(row["timestamp"]) <= ending, "posting outside period")
        net += debit - credit
        if row["payment_id"] is not None:
            _need(row["payment_id"] in payments, "orphan payment posting")
            journal_payment[row["payment_id"]].append(row)
        elif row["invoice_id"] is not None:
            _need(row["invoice_id"] in invoices, "orphan invoice posting")
            journal_invoice[row["invoice_id"]].append(row)
        else:
            opening.append(row)
    _need(net == 0, "unbalanced total ledger")

    derived = []
    obligations = defaultdict(list)
    payable_id = {}
    for inv in invoices.values():
        iid, lines = inv["invoice_id"], inv["line_items"]
        _need(_amount(inv["total_minor"]) and isinstance(lines, list) and lines
              and all(_amount(x["amount_minor"]) for x in lines)
              and sum(x["amount_minor"] for x in lines) == inv["total_minor"],
              "invoice line sum or total invalid")
        _need(beginning <= moment(inv["issued_at"]) <= ending
              and moment(inv["due_at"]) >= moment(inv["issued_at"]),
              "invoice timestamp or due date invalid")
        services = {line["service_ref"] for line in lines}
        _need(len(services) == 1, "multiple service obligations in invoice")
        obligations[(inv["entity_id"], next(iter(services)))].append(inv)
        rate, rate_id = quote(inv["currency"], inv["issued_at"])
        exact = _converted(inv["total_minor"], rate)
        allocations = [_converted(line["amount_minor"], rate) for line in lines[:-1]]
        allocations.append(exact - sum(allocations))
        _need(all(value > 0 for value in allocations), "rounding residual invalid")
        rows = journal_invoice[iid]
        expense = {r["line_id"]: r for r in rows if r["account"] == "expense"}
        payable = [r for r in rows if r["account"] == "payable"]
        _need(len(rows) == len(lines) + 1 and len(expense) == len(lines)
              and len(payable) == 1, "invoice journal shape invalid")
        row = payable[0]
        payable_id[iid] = row["row_id"]
        _need(row["credit_minor"] == exact and row["debit_minor"] == 0,
              "invoice payable total differs from source document")
        for line, value in zip(lines, allocations):
            e = expense.get(line["line_id"])
            _need(e is not None and e["debit_minor"] == value and e["credit_minor"] == 0,
                  "invoice expense differs from line and rounding")
        _need(all(r["entity_id"] == inv["entity_id"] and
                  moment(r["timestamp"]) == moment(inv["issued_at"]) and
                  r["rate_id"] == rate_id for r in rows),
              "invoice posting scope/FX inconsistent")
        periods = {r["reporting_period"] for r in rows}
        _need(len(periods) == 1, "mixed report periods within invoice")
        if next(iter(periods)) != moment(inv["issued_at"]).strftime("%Y-%m"):
            derived.append(_issue("reporting_period", [iid], exact, "KZT",
                                  [inv["doc_id"], row["row_id"]]))
    for group in obligations.values():
        _need(len(group) <= 2, "ambiguous repeated economic obligation")
        if len(group) == 2:
            a, b = group
            _need(a["currency"] == b["currency"] and
                  a["total_minor"] == b["total_minor"], "unresolvable duplicate")
            derived.append(_issue("duplicate_invoice",
                                  [a["invoice_id"], b["invoice_id"]], a["total_minor"],
                                  a["currency"],
                                  [a["doc_id"], b["doc_id"], payable_id[a["invoice_id"]],
                                   payable_id[b["invoice_id"]]]))
    paid = defaultdict(int)
    total_outflow = 0
    for payment in payments.values():
        target = invoices.get(payment["remittance_invoice_id"])
        _need(target is not None, "orphan remittance")
        pid = payment["payment_id"]
        amount, stamp = payment["amount_minor"], payment["timestamp"]
        _need(_amount(amount) and payment["currency"] == target["currency"],
              "payment amount/currency inconsistent")
        _need(beginning <= moment(stamp) <= ending and
              moment(stamp).date() == moment(target["issued_at"]).date(),
              "payment outside remittance date")
        paid[target["invoice_id"]] += amount
        _need(paid[target["invoice_id"]] <= target["total_minor"],
              "remittance exceeds invoice")
        refs = payment["invoice_refs"]
        _need(isinstance(refs, list), "payment allocations not a list")
        _need(len({r["invoice_id"] for r in refs}) == len(refs), "duplicate allocation row")
        allocated = 0
        other_docs = []
        for r in refs:
            source = invoices.get(r["invoice_id"])
            _need(source is not None and _amount(r["amount_minor"]) and
                  source["currency"] == target["currency"] and
                  source["entity_id"] == target["entity_id"], "allocation references unknown business")
            allocated += r["amount_minor"]
            other_docs.append(source["doc_id"])
        _need(allocated <= amount, "overallocated payment")
        journal = journal_payment[pid]
        debit = [r for r in journal if r["account"] == "payable"]
        credit = [r for r in journal if r["account"] == "bank"]
        _need(len(journal) == 2 and len(debit) == len(credit) == 1,
              "incomplete payment journal")
        ap, bank = debit[0], credit[0]
        _need(ap["debit_minor"] == bank["credit_minor"]
              and ap["credit_minor"] == bank["debit_minor"] == 0,
              "unbalanced payment posting")
        _need(all(r["entity_id"] == target["entity_id"]
                  and r["invoice_id"] == target["invoice_id"]
                  and moment(r["timestamp"]) == moment(stamp)
                  and r["reporting_period"] == moment(stamp).strftime("%Y-%m") for r in journal),
              "payment journal scope or cutoff inconsistent")
        rate, correct_id = quote(payment["currency"], stamp)
        used_id = ap["rate_id"]
        _need(bank["rate_id"] == used_id, "payment journal FX disagreement")
        applied = fx_by_id.get(used_id)
        if payment["currency"] != "KZT":
            _need(applied is not None and
                  ap["debit_minor"] == _converted(amount, applied["rate"]),
                  "journal incompatible with applied FX rate")
        else:
            _need(used_id is None and ap["debit_minor"] == amount,
                  "base-currency payment conversion invalid")
        expected = _converted(amount, rate)
        gap = abs(expected - ap["debit_minor"])
        if gap or used_id != correct_id:
            derived.append(_issue("fx_rate_or_date", [pid, ap["row_id"]],
                                  gap, "KZT",
                                  [target["doc_id"], payment["doc_id"],
                                   ap["row_id"], bank["row_id"], correct_id]))
        actual_on_target = sum(ref["amount_minor"] for ref in refs
                               if ref["invoice_id"] == target["invoice_id"])
        if actual_on_target != amount:
            evidence = [target["doc_id"], payment["doc_id"],
                        ap["row_id"], bank["row_id"], *other_docs]
            if correct_id is not None:
                evidence.append(correct_id)
            derived.append(_issue("payment_allocation", [target["invoice_id"], pid],
                                  _converted(amount - actual_on_target, rate), "KZT",
                                  evidence))
        total_outflow += bank["credit_minor"]
    _need(len(opening) == 2, "opening journal cardinality")
    initial_bank = [r for r in opening if r["account"] == "bank"]
    initial_equity = [r for r in opening if r["account"] == "equity"]
    _need(len(initial_bank) == len(initial_equity) == 1 and
          initial_bank[0]["debit_minor"] == initial_equity[0]["credit_minor"] and
          initial_bank[0]["debit_minor"] >= total_outflow,
          "opening funding/account mismatch")
    issue_count = verify_truth_evidence(derived, truth, public)
    return {"status": "PASS", "model": "accrual_company_v1",
            "issues_audited": issue_count, "journal_rows": len(t["ledger"]),
            "invoice_count": len(invoices), "payment_count": len(payments),
            "journal_net_minor": net, "independent_derivation": True}
