"""Independent public-data financial validation for accrual_company_v2.

This validator intentionally does not read generator provenance or fault truth
to derive financial correctness. It uses Fraction, not the generator's Decimal.
Only clean split/supplier-refund scenarios under the explicitly versioned
policy are accepted. Not a general accounting or audit standards engine.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import re


_ZONE = timezone(timedelta(hours=5))
_REQUIRED = {
    "accounting_model": "accrual_company_v2",
    "allocation_rule": "explicit_same_currency_invoice_refs",
    "payment_journal_basis": "vendor_ap_control",
    "refund_rule": "linked_after_all_positive_payments",
    "refund_currency": "KZT",
    "refund_invoice_effect": "restore_outstanding",
    "fx_date": "local_transaction_date",
    "rounding": "ROUND_HALF_EVEN",
    "period_rule": "calendar_month_of_transaction",
}


def _check(ok, label):
    if not ok:
        raise ValueError(label)


def _instant(value):
    _check(isinstance(value, str), "timestamp must be text")
    try:
        instant = datetime.fromisoformat(value)
        _check(instant.utcoffset() is not None, "timezone offset missing")
        return instant.astimezone(_ZONE)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid timezone timestamp") from exc


def _int(value):
    return type(value) is int and value > 0


def _converted(amount, rate):
    _check(_int(amount), "nonpositive or noninteger money")
    number = Fraction(amount) * Fraction(str(rate))
    whole, tail = divmod(number.numerator, number.denominator)
    return whole + int(2 * tail > number.denominator or
                       (2 * tail == number.denominator and whole % 2 == 1))


def validate_settlement_company(public, truth):
    """Reject inconsistent six-file financial histories; accept only empty truth.

    Returns diagnostic net per-invoice paid/outstanding native minor units.
    No private labels or source generator methods are used by this function.
    """
    _check(type(public) is dict and type(truth) is dict and truth == {"issues": []},
           "settlement_v2 is clean-only")
    manifest, policy, tables = public["manifest"], public["policy"], public["tables"]
    _check(manifest.get("schema_version") == "0.4-company-settlements", "wrong settlement schema")
    _check(manifest.get("base_currency") == "KZT" and manifest.get("timezone") == "+05:00",
           "unsupported base currency/timezone")
    _check(all(policy.get(k) == v for k, v in _REQUIRED.items()), "unsupported settlement policy")
    _check(policy.get("currency_exponents") == {"KZT": 2, "USD": 2},
           "unsupported currency exponents")
    _check(set(tables) == {"invoices", "payments", "ledger", "fx"}, "wrong public tables")
    _check(manifest["counts"] == {k: len(v) for k, v in tables.items()},
           "public record counts inconsistent")
    _check(200 <= len(tables["ledger"]) <= 2000 and
           20 <= len(tables["payments"]) + len(tables["invoices"]) <= 200,
           "episode size outside supported range")
    start, end = _instant(manifest["period_start"]), _instant(manifest["period_end"])
    _check(start <= end, "invalid period")

    all_ids = set()
    def register(value):
        _check(isinstance(value, str) and 0 < len(value) <= 128 and value not in all_ids,
               "duplicate or invalid public identifier")
        all_ids.add(value)

    for name, key in (("invoices", "invoice_id"), ("payments", "payment_id"),
                      ("ledger", "row_id"), ("fx", "rate_id")):
        for row in tables[name]:
            register(row[key])
            if name in ("invoices", "payments"):
                register(row["doc_id"])

    fx_dates, rate_by_id = {}, {}
    for rate in tables["fx"]:
        _check(rate["source_currency"] == "USD" and rate["target_currency"] == "KZT",
               "wrong FX pair")
        _check(isinstance(rate["rate"], str) and
               re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", rate["rate"]) is not None and
               Fraction(rate["rate"]) > 0, "invalid FX quote")
        _check(rate["date"] not in fx_dates and
               datetime.fromisoformat(rate["date"]).date().isoformat() == rate["date"],
               "duplicate/invalid FX date")
        fx_dates[rate["date"]] = rate
        rate_by_id[rate["rate_id"]] = rate

    def quote(currency, timestamp):
        if currency == "KZT":
            return "1", None
        _check(currency == "USD", "unsupported currency")
        d = _instant(timestamp).date().isoformat()
        _check(d in fx_dates, "FX date not published")
        rate = fx_dates[d]
        return rate["rate"], rate["rate_id"]

    invoices = {row["invoice_id"]: row for row in tables["invoices"]}
    payments = {row["payment_id"]: row for row in tables["payments"]}
    rows_invoice, rows_payment, opening = defaultdict(list), defaultdict(list), []
    seen_services = set()
    debits = credits = 0
    for entry in tables["ledger"]:
        debit, credit = entry["debit_minor"], entry["credit_minor"]
        _check(type(debit) is type(credit) is int and debit >= 0 and credit >= 0 and
               (debit > 0) != (credit > 0), "invalid journal posting")
        _check(entry["currency"] == "KZT", "all posted money must use base currency")
        _check(start <= _instant(entry["timestamp"]) <= end, "journal timestamp outside period")
        _check(entry["reporting_period"] == _instant(entry["timestamp"]).strftime("%Y-%m"),
               "journal cutoff incorrect")
        debits += debit
        credits += credit
        pid, iid = entry["payment_id"], entry["invoice_id"]
        if pid is not None:
            _check(pid in payments, "orphan payment journal")
            rows_payment[pid].append(entry)
        elif iid is not None:
            _check(iid in invoices, "orphan invoice journal")
            rows_invoice[iid].append(entry)
        else:
            opening.append(entry)
    _check(debits == credits, "journal not balanced")

    for invoice in invoices.values():
        iid = invoice["invoice_id"]
        issued_at, due_at = _instant(invoice["issued_at"]), _instant(invoice["due_at"])
        _check(start <= issued_at <= end and due_at >= issued_at, "invalid invoice dates")
        _check(_int(invoice["total_minor"]) and invoice["currency"] in ("KZT", "USD"),
               "invalid invoice money")
        lines = invoice["line_items"]
        _check(isinstance(lines, list) and lines and
               all(_int(line["amount_minor"]) for line in lines) and
               sum(line["amount_minor"] for line in lines) == invoice["total_minor"],
               "invoice component totals invalid")
        service_refs = {line["service_ref"] for line in lines}
        _check(len(service_refs) == 1, "mixed service identity")
        service = next(iter(service_refs))
        identity = (invoice["entity_id"], service)
        _check(identity not in seen_services, "duplicate economic obligation")
        seen_services.add(identity)
        rate, rate_id = quote(invoice["currency"], invoice["issued_at"])
        converted = _converted(invoice["total_minor"], rate)
        amounts = [_converted(line["amount_minor"], rate) for line in lines[:-1]]
        amounts.append(converted - sum(amounts))
        _check(all(amount > 0 for amount in amounts), "rounding created nonpositive component")
        journal = rows_invoice[iid]
        _check(len(journal) == len(lines) + 1, "invoice journal incomplete")
        payable = [x for x in journal if x["account"] == "payable"]
        expenses = [x for x in journal if x["account"] == "expense"]
        _check(len(payable) == 1 and len(expenses) == len(lines), "invoice account mismatch")
        ap = payable[0]
        _check(ap["debit_minor"] == 0 and ap["credit_minor"] == converted and
               ap["line_id"] is None, "invoice payable mismatch")
        by_line = {x["line_id"]: x for x in expenses}
        _check(len(by_line) == len(lines), "repeated invoice line journal")
        for line, amount in zip(lines, amounts):
            register(line["line_id"])
            _check(line["line_id"] in by_line and by_line[line["line_id"]]["debit_minor"] == amount
                   and by_line[line["line_id"]]["credit_minor"] == 0, "invoice expense mismatch")
        _check(all(x["entity_id"] == invoice["entity_id"] and
                   _instant(x["timestamp"]) == issued_at and
                   x["rate_id"] == rate_id for x in journal),
               "invoice journal rate/entity/date mismatch")

    normal = {k: p for k, p in payments.items() if p.get("kind") == "payment"}
    refunds = {k: p for k, p in payments.items() if p.get("kind") == "refund"}
    _check(len(normal) + len(refunds) == len(payments), "unsupported payment movement type")
    _check(len(normal) > 0 and len(refunds) > 0, "clean split/refund required")
    outstanding = {iid: i["total_minor"] for iid, i in invoices.items()}
    applied = defaultdict(int)
    original_allocations = {}
    net_cash_outflow = 0
    split_count = 0
    latest_normal = max(_instant(p["timestamp"]) for p in normal.values())

    # Apply positive transfers in chronological order and check document-level
    # allocation independently of the production payment_matching implementation.
    for payment in sorted(normal.values(), key=lambda p: (_instant(p["timestamp"]), p["payment_id"])):
        pid, stamp = payment["payment_id"], _instant(payment["timestamp"])
        amount, entity, currency = payment["amount_minor"], payment["entity_id"], payment["currency"]
        _check(_int(amount), "nonpositive payment")
        references = payment["invoice_refs"]
        _check(isinstance(references, list) and references, "missing payment invoice references")
        _check(len(references) == len({ref["invoice_id"] for ref in references}),
               "duplicate payment invoice references")
        _check(sum(ref["amount_minor"] for ref in references) == amount and
               all(_int(ref["amount_minor"]) for ref in references), "payment allocation sum incorrect")
        _check(all(ref["invoice_id"] in invoices and
                   invoices[ref["invoice_id"]]["entity_id"] == entity and
                   invoices[ref["invoice_id"]]["currency"] == currency and
                   _instant(invoices[ref["invoice_id"]]["issued_at"]) <= stamp
                   for ref in references), "payment reference entity/currency/date mismatch")
        for ref in references:
            iid, value = ref["invoice_id"], ref["amount_minor"]
            _check(value <= outstanding[iid], "payment over-allocated invoice")
            outstanding[iid] -= value
            applied[iid] += value
            original_allocations[(pid, iid)] = value
        if len(references) > 1:
            split_count += 1
        journal = rows_payment[pid]
        _check(len(journal) == 2, "payment journal missing or duplicated rows")
        ap = [x for x in journal if x["account"] == "payable"]
        bank = [x for x in journal if x["account"] == "bank"]
        _check(len(ap) == len(bank) == 1, "payment account pairs invalid")
        rate, rate_id = quote(currency, payment["timestamp"])
        converted = _converted(amount, rate)
        _check(ap[0]["debit_minor"] == converted and ap[0]["credit_minor"] == 0 and
               bank[0]["credit_minor"] == converted and bank[0]["debit_minor"] == 0,
               "payment journal cash/AP conversion mismatch")
        single_iid = references[0]["invoice_id"] if len(references) == 1 else None
        _check(payment.get("remittance_invoice_id") == single_iid, "ambiguous remittance anchor")
        _check(all(x["entity_id"] == entity and x["invoice_id"] == single_iid and
                   x["line_id"] is None and x["rate_id"] == rate_id and
                   _instant(x["timestamp"]) == stamp for x in journal),
               "payment posting scope mismatch")
        net_cash_outflow += converted
    _check(split_count > 0, "missing clean split case")

    claimed = defaultdict(int)
    for refund in sorted(refunds.values(), key=lambda p: p["payment_id"]):
        rid, origin_id, amount = refund["payment_id"], refund["original_payment_id"], refund["amount_minor"]
        _check(origin_id in normal, "unknown refund original payment")
        origin = normal[origin_id]
        stamp = _instant(refund["timestamp"])
        _check(stamp > latest_normal and start <= stamp <= end, "refund timing invalid")
        _check(refund["currency"] == origin["currency"] == "KZT" and
               refund["entity_id"] == origin["entity_id"], "refund source currency/entity mismatch")
        _check(_int(amount) and refund.get("remittance_invoice_id") is None,
               "refund amount or remittance anchor invalid")
        references = refund["invoice_refs"]
        _check(isinstance(references, list) and references and
               len(references) == len({ref["invoice_id"] for ref in references}) and
               all(_int(ref["amount_minor"]) for ref in references) and
               sum(ref["amount_minor"] for ref in references) == amount,
               "refund references invalid")
        for ref in references:
            iid, value = ref["invoice_id"], ref["amount_minor"]
            _check((origin_id, iid) in original_allocations, "refund refers to unrelated invoice")
            claimed[(origin_id, iid)] += value
            _check(claimed[(origin_id, iid)] <= original_allocations[(origin_id, iid)],
                   "refund exceeds source payment allocation")
            applied[iid] -= value
            outstanding[iid] += value
        journal = rows_payment[rid]
        _check(len(journal) == 2, "refund journal incomplete")
        ap = [x for x in journal if x["account"] == "payable"]
        bank = [x for x in journal if x["account"] == "bank"]
        _check(len(ap) == len(bank) == 1, "refund account pair invalid")
        _check(ap[0]["debit_minor"] == 0 and ap[0]["credit_minor"] == amount and
               bank[0]["debit_minor"] == amount and bank[0]["credit_minor"] == 0,
               "refund reversal posting invalid")
        _check(all(x["invoice_id"] is None and x["entity_id"] == refund["entity_id"]
                   and x["line_id"] is None and x["rate_id"] is None and
                   _instant(x["timestamp"]) == stamp for x in journal),
               "refund ledger identity/date mismatch")
        net_cash_outflow -= amount

    _check(all(applied[iid] + outstanding[iid] == invoices[iid]["total_minor"] and
               0 <= applied[iid] <= invoices[iid]["total_minor"] for iid in invoices),
           "net invoice balances impossible")
    _check(len(opening) == 2, "opening journal incomplete")
    capital_bank = [r for r in opening if r["account"] == "bank"]
    equity = [r for r in opening if r["account"] == "equity"]
    _check(len(capital_bank) == len(equity) == 1 and
           capital_bank[0]["debit_minor"] == equity[0]["credit_minor"] and
           capital_bank[0]["credit_minor"] == equity[0]["debit_minor"] == 0 and
           capital_bank[0]["debit_minor"] >= net_cash_outflow and
           all(r["entity_id"] == manifest["company_id"] and
               _instant(r["timestamp"]) == start for r in opening),
           "opening capital insufficient or inconsistent")
    return {
        "split_payments": split_count,
        "refunds": len(refunds),
        "balances": {iid: {"currency": invoice["currency"], "paid_minor": applied[iid],
                           "outstanding_minor": outstanding[iid]}
                     for iid, invoice in sorted(invoices.items())},
    }
