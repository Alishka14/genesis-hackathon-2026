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


def audit_v2(public, truth):
    """Second implementation of bounded v2 split/refund financial semantics.

    Checks invoice posting amounts, transfers, remittance basis, refunds and
    derived evidence from the six public files without calling v2 production
    validators. Does not approve arbitrary accounting rules or netting.
    """
    _need(isinstance(public, dict) and isinstance(public.get("tables"), dict),
          "bad v2 public data")
    manifest, policy, t = public["manifest"], public["policy"], public["tables"]
    _need(policy["accounting_model"] == "accrual_company_v2"
          and manifest["schema_version"] == "0.4-company-settlements"
          and manifest["base_currency"] == "KZT"
          and manifest["timezone"] == policy["cutoff_timezone"] == "+05:00",
          "unsupported settlement model")
    _need(set(t) == {"invoices", "payments", "ledger", "fx"}
          and manifest["counts"] == {key: len(rows) for key, rows in t.items()},
          "v2 manifest/table inventory")
    def moment(value):
        stamp = datetime.fromisoformat(value)
        _need(stamp.utcoffset() is not None, "missing v2 timestamp offset")
        return stamp.astimezone(timezone(timedelta(hours=5)))
    start, end = moment(manifest["period_start"]), moment(manifest["period_end"])
    rates = {}
    for rate in t["fx"]:
        _need(rate["source_currency"] == "USD"
              and rate["target_currency"] == "KZT"
              and rate["date"] not in rates, "v2 malformed FX rate")
        rates[rate["date"]] = rate
    def convert(currency, amount, stamp):
        if currency == "KZT":
            return amount, None
        _need(currency == "USD", "v2 foreign currency not supported")
        rate = rates.get(moment(stamp).date().isoformat())
        _need(rate is not None, "v2 missing rate")
        return _converted(amount, rate["rate"]), rate["rate_id"]
    invoices = {x["invoice_id"]: x for x in t["invoices"]}
    payments = {x["payment_id"]: x for x in t["payments"]}
    _need(len(invoices) == len(t["invoices"])
          and len(payments) == len(t["payments"]), "duplicate business source IDs")
    public_ids = []
    for table, key in (("invoices", "invoice_id"), ("payments", "payment_id"),
                       ("ledger", "row_id"), ("fx", "rate_id")):
        for record in t[table]:
            public_ids.append(record[key])
            if table in ("invoices", "payments"):
                public_ids.append(record["doc_id"])
    _need(all(isinstance(item, str) and item for item in public_ids)
          and len(public_ids) == len(set(public_ids)), "duplicate v2 public ID")
    journal_invoice, journal_payment, capital = defaultdict(list), defaultdict(list), []
    net = 0
    for row in t["ledger"]:
        debit, credit = row["debit_minor"], row["credit_minor"]
        _need(type(debit) is type(credit) is int and debit >= 0 and credit >= 0
              and (debit > 0) != (credit > 0) and row["currency"] == "KZT",
              "v2 journal money invalid")
        _need(start <= moment(row["timestamp"]) <= end
              and row["reporting_period"] == moment(row["timestamp"]).strftime("%Y-%m"),
              "v2 journal cutoff invalid")
        net += debit - credit
        if row["payment_id"] is not None:
            _need(row["payment_id"] in payments, "unknown v2 payment journal")
            journal_payment[row["payment_id"]].append(row)
        elif row["invoice_id"] is not None:
            _need(row["invoice_id"] in invoices, "unknown v2 invoice journal")
            journal_invoice[row["invoice_id"]].append(row)
        else:
            capital.append(row)
    _need(net == 0, "v2 debit/credit imbalance")
    payable_id = {}
    obligations = defaultdict(list)
    for inv in invoices.values():
        lines = inv["line_items"]
        _need(_amount(inv["total_minor"]) and lines
              and all(_amount(x["amount_minor"]) for x in lines)
              and sum(x["amount_minor"] for x in lines) == inv["total_minor"],
              "v2 invoice line/total mismatch")
        _need(start <= moment(inv["issued_at"]) <= end
              and moment(inv["due_at"]) >= moment(inv["issued_at"]),
              "v2 invoice date invalid")
        refs = {x["service_ref"] for x in lines}
        _need(len(refs) == 1, "v2 invoice mixed service")
        obligations[(inv["entity_id"], next(iter(refs)))].append(inv)
        total, fxid = convert(inv["currency"], inv["total_minor"], inv["issued_at"])
        parts = [convert(inv["currency"], x["amount_minor"], inv["issued_at"])[0]
                 for x in lines[:-1]]
        parts.append(total - sum(parts))
        rows = journal_invoice[inv["invoice_id"]]
        ap = [x for x in rows if x["account"] == "payable"]
        expense = {x["line_id"]: x for x in rows if x["account"] == "expense"}
        _need(len(rows) == len(lines) + 1 and len(ap) == 1 and
              len(expense) == len(lines), "v2 invoice posting cardinality")
        payable_id[inv["invoice_id"]] = ap[0]["row_id"]
        _need(ap[0]["credit_minor"] == total and ap[0]["debit_minor"] == 0,
              "v2 payable FX total mismatch")
        for line, value in zip(lines, parts):
            row = expense.get(line["line_id"])
            _need(row is not None and row["debit_minor"] == value
                  and row["credit_minor"] == 0, "v2 invoice component posting")
        _need(all(row["entity_id"] == inv["entity_id"]
                  and moment(row["timestamp"]) == moment(inv["issued_at"])
                  and row["rate_id"] == fxid for row in rows),
              "v2 invoice posting provenance")
    derived = []
    for group in obligations.values():
        _need(len(group) <= 2, "v2 too many matching service obligations")
        if len(group) == 2:
            x, y = group
            _need(x["currency"] == y["currency"]
                  and x["total_minor"] == y["total_minor"],
                  "v2 duplicate invoice ambiguous")
            derived.append(_issue("duplicate_invoice",
                                  [x["invoice_id"], y["invoice_id"]],
                                  x["total_minor"], x["currency"],
                                  [x["doc_id"], y["doc_id"],
                                   payable_id[x["invoice_id"]],
                                   payable_id[y["invoice_id"]]]))
    original_allocations = {}
    applied = defaultdict(int)
    outflow = 0
    transfer_times = []
    normal = [p for p in payments.values() if p["kind"] == "payment"]
    refunds = [p for p in payments.values() if p["kind"] == "refund"]
    _need(normal and refunds and len(normal) + len(refunds) == len(payments),
          "v2 unsupported payment kind")
    for p in sorted(normal, key=lambda p: (moment(p["timestamp"]), p["payment_id"])):
        pid, stamp = p["payment_id"], moment(p["timestamp"])
        _need(start <= stamp <= end and _amount(p["amount_minor"]), "v2 bad normal payment")
        actual = p["invoice_refs"]
        _need(isinstance(actual, list) and actual
              and len({x["invoice_id"] for x in actual}) == len(actual),
              "v2 invalid invoice reference list")
        _need(all(x["invoice_id"] in invoices and _amount(x["amount_minor"])
                  and invoices[x["invoice_id"]]["currency"] == p["currency"]
                  and invoices[x["invoice_id"]]["entity_id"] == p["entity_id"]
                  and moment(invoices[x["invoice_id"]]["issued_at"]) <= stamp
                  for x in actual), "v2 payment reference scope invalid")
        basis = p.get("allocation_basis")
        if basis is not None:
            _need(len(basis) == 2 and len(actual) == 2 and
                  p["currency"] == "KZT", "v2 documented split malformed")
            expected = {x["invoice_id"]: x["amount_minor"] for x in basis}
            applied_refs = {x["invoice_id"]: x["amount_minor"] for x in actual}
            _need(set(expected) == set(applied_refs)
                  and len(expected) == 2
                  and sum(expected.values()) == p["amount_minor"],
                  "v2 documented split mismatch")
            differences = {iid: expected[iid] - applied_refs[iid] for iid in expected
                           if expected[iid] != applied_refs[iid]}
            _need(len(differences) <= 1 and
                  all(value > 0 for value in differences.values()),
                  "v2 unsupported split discrepancy")
            if differences:
                iid, amount = next(iter(differences.items()))
                payable = [r for r in journal_payment[pid] if r["account"] == "payable"]
                _need(len(payable) == 1, "v2 missing payment payable evidence")
                derived.append(_issue("payment_allocation", [iid, pid], amount, "KZT",
                                      [p["doc_id"], payable[0]["row_id"],
                                       *[invoices[name]["doc_id"] for name in expected]]))
        else:
            _need(sum(x["amount_minor"] for x in actual) == p["amount_minor"],
                  "v2 normal transfer unallocated")
        _need(sum(x["amount_minor"] for x in actual) <= p["amount_minor"],
              "v2 payment money created")
        for ref in actual:
            applied[ref["invoice_id"]] += ref["amount_minor"]
            original_allocations[(pid, ref["invoice_id"])] = ref["amount_minor"]
        converted, fxid = convert(p["currency"], p["amount_minor"], p["timestamp"])
        rows = journal_payment[pid]
        payable = [r for r in rows if r["account"] == "payable"]
        bank = [r for r in rows if r["account"] == "bank"]
        _need(len(rows) == 2 and len(payable) == len(bank) == 1
              and payable[0]["debit_minor"] == bank[0]["credit_minor"] == converted
              and payable[0]["credit_minor"] == bank[0]["debit_minor"] == 0,
              "v2 payment journal not accounted")
        expected_anchor = actual[0]["invoice_id"] if len(actual) == 1 else None
        _need(p.get("remittance_invoice_id") == expected_anchor,
              "v2 transfer remittance anchor invalid")
        _need(all(x["entity_id"] == p["entity_id"]
                  and x["invoice_id"] == expected_anchor
                  and x["line_id"] is None and x["rate_id"] == fxid
                  and moment(x["timestamp"]) == stamp
                  for x in rows), "v2 transfer posting source wrong")
        transfer_times.append(stamp)
        outflow += converted
    refunded = defaultdict(int)
    for p in refunds:
        origin_id = p["original_payment_id"]
        origin = payments.get(origin_id)
        _need(origin in normal and p["currency"] == origin["currency"] == "KZT"
              and p["entity_id"] == origin["entity_id"]
              and moment(p["timestamp"]) > max(transfer_times),
              "v2 unmatched refund source/time")
        _need(_amount(p["amount_minor"]) and
              sum(x["amount_minor"] for x in p["invoice_refs"]) == p["amount_minor"],
              "v2 refund sum invalid")
        for x in p["invoice_refs"]:
            key = (origin_id, x["invoice_id"])
            _need(key in original_allocations and _amount(x["amount_minor"]),
                  "v2 refund references unrelated invoice")
            refunded[key] += x["amount_minor"]
            _need(refunded[key] <= original_allocations[key], "v2 over-refund")
            applied[x["invoice_id"]] -= x["amount_minor"]
        rows = journal_payment[p["payment_id"]]
        payable = [r for r in rows if r["account"] == "payable"]
        bank = [r for r in rows if r["account"] == "bank"]
        _need(len(rows) == 2 and len(payable) == len(bank) == 1
              and payable[0]["credit_minor"] == bank[0]["debit_minor"] == p["amount_minor"]
              and payable[0]["debit_minor"] == bank[0]["credit_minor"] == 0,
              "v2 refund accounting mismatch")
        _need(p.get("remittance_invoice_id") is None and
              all(x["invoice_id"] is None and x["entity_id"] == p["entity_id"]
                  and x["line_id"] is None and x["rate_id"] is None
                  and moment(x["timestamp"]) == moment(p["timestamp"])
                  for x in rows), "v2 refund journal source/date invalid")
        outflow -= p["amount_minor"]
    _need(all(0 <= applied[iid] <= inv["total_minor"] for iid, inv in invoices.items()),
          "v2 applied invoice balance impossible")
    bank = [r for r in capital if r["account"] == "bank"]
    equity = [r for r in capital if r["account"] == "equity"]
    _need(len(capital) == 2 and len(bank) == len(equity) == 1
          and bank[0]["debit_minor"] == equity[0]["credit_minor"]
          and bank[0]["credit_minor"] == equity[0]["debit_minor"] == 0
          and bank[0]["debit_minor"] >= outflow
          and all(x["entity_id"] == manifest["company_id"]
                  and x["invoice_id"] is None and x["payment_id"] is None
                  and x["line_id"] is None and x["rate_id"] is None
                  and moment(x["timestamp"]) == start for x in capital),
          "v2 capital inadequate")
    count = verify_truth_evidence(derived, truth, public)
    return {"status": "PASS", "model": "accrual_company_v2",
            "issues_audited": count, "journal_rows": len(t["ledger"]),
            "invoice_count": len(invoices), "payment_count": len(payments),
            "refund_count": len(refunds), "journal_net_minor": net,
            "independent_derivation": True}


def audit_company(public, truth):
    """Dispatch only versioned synthetic models within trusted evaluator code."""
    model = public["policy"].get("accounting_model")
    if model == "accrual_company_v1":
        return audit_v1(public, truth)
    if model == "accrual_company_v2":
        return audit_v2(public, truth)
    raise ValueError("independent audit: unsupported accounting model")
