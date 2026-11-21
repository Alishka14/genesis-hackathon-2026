"""Independent public-data audit for the documented accrual_company_v1 model.

No imports of LedgerWorld, company_checks, baselines or private truth.
Fraction arithmetic deliberately differs from the generator's Decimal arithmetic.
This cross-check is NOT professional audit certification or organizer acceptance.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction

_ZONE = timezone(timedelta(hours=5))


def _require(value, message):
    if not value:
        raise ValueError(message)


def _time(value):
    dt = datetime.fromisoformat(value)
    _require(dt.utcoffset() is not None, "timestamp requires offset")
    return dt.astimezone(_ZONE)


def _round_minor(amount, rate):
    ratio = Fraction(amount) * Fraction(str(rate))
    whole, remainder = divmod(ratio.numerator, ratio.denominator)
    return whole + int(2 * remainder > ratio.denominator or
                       (2 * remainder == ratio.denominator and whole % 2 == 1))


def _key(kind, ids, amount, currency):
    return kind, tuple(sorted(ids)), amount, currency


def audit_company_public(public):
    """Return issue signatures inferred from public records alone.

    Raises ValueError if the financial model itself is inconsistent.
    Supported scope: the published LedgerGym accrual_company_v1 synthetic policy.
    """
    manifest, policy, tables = public["manifest"], public["policy"], public["tables"]
    _require(policy.get("accounting_model") == "accrual_company_v1" and
             policy.get("fx_date") == "local_transaction_date" and
             policy.get("rounding") == "ROUND_HALF_EVEN" and
             policy.get("allocation_rule") == "allocate_full_payment_to_remittance_invoice" and
             policy.get("period_rule") == "calendar_month_of_transaction", "unsupported policy")
    _require(manifest["base_currency"] == "KZT" and manifest["timezone"] == "+05:00", "unsupported base settings")
    _require(set(tables) == {"ledger", "invoices", "payments", "fx"}, "unexpected table")
    _require(manifest["counts"] == {k: len(v) for k, v in tables.items()}, "record counts mismatch")
    ledger, invoices, payments, fx = [tables[k] for k in ("ledger", "invoices", "payments", "fx")]
    _require(all(type(r["debit_minor"]) is int and type(r["credit_minor"]) is int and
                 r["debit_minor"] >= 0 and r["credit_minor"] >= 0 and
                 (r["debit_minor"] > 0) != (r["credit_minor"] > 0)
                 for r in ledger), "invalid posting")
    _require(sum(r["debit_minor"] - r["credit_minor"] for r in ledger) == 0, "journal not balanced")
    inv = {x["invoice_id"]: x for x in invoices}
    pay = {x["payment_id"]: x for x in payments}
    rates = {x["date"]: x for x in fx}
    rates_by_id = {x["rate_id"]: x for x in fx}
    _require(len(inv) == len(invoices) and len(pay) == len(payments) and
             len(rates) == len(rates_by_id) == len(fx), "duplicate document or rate ID")

    def quote(currency, timestamp):
        if currency == "KZT":
            return "1", None
        _require(currency == "USD", "unsupported currency")
        record = rates[_time(timestamp).date().isoformat()]
        _require(record["source_currency"] == "USD" and record["target_currency"] == "KZT", "invalid rate")
        return record["rate"], record["rate_id"]

    invoice_rows, payment_rows = defaultdict(list), defaultdict(list)
    for r in ledger:
        _require(r["currency"] == "KZT", "incorrect ledger currency")
        if r["payment_id"] is not None:
            _require(r["payment_id"] in pay, "orphan payment")
            payment_rows[r["payment_id"]].append(r)
        elif r["invoice_id"] is not None:
            _require(r["invoice_id"] in inv, "orphan invoice")
            invoice_rows[r["invoice_id"]].append(r)

    signatures, evidence, obligations, credits = [], {}, defaultdict(list), {}

    def add(kind, ids, amount, currency, docs):
        signature = _key(kind, ids, amount, currency)
        _require(signature not in evidence, "duplicate derived issue")
        signatures.append(signature)
        evidence[signature] = set(docs)

    for invoice in invoices:
        iid = invoice["invoice_id"]
        lines = invoice["line_items"]
        _require(type(invoice["total_minor"]) is int and invoice["total_minor"] > 0 and
                 lines and sum(x["amount_minor"] for x in lines) == invoice["total_minor"], "invalid invoice totals")
        service_ids = {x["service_ref"] for x in lines}
        _require(len(service_ids) == 1, "unsupported multi-service invoice")
        obligations[(invoice["entity_id"], next(iter(service_ids)))].append(invoice)
        currency, amount = invoice["currency"], invoice["total_minor"]
        exchange_rate, rate_id = quote(currency, invoice["issued_at"])
        expected = _round_minor(amount, exchange_rate)
        rows = invoice_rows[iid]
        expense = {r["line_id"]: r for r in rows if r["account"] == "expense"}
        liability = [r for r in rows if r["account"] == "payable"]
        _require(len(rows) == len(lines) + 1 and len(expense) == len(lines) and len(liability) == 1,
                 "invoice journal incomplete")
        credit = liability[0]
        credits[iid] = credit
        parts = [_round_minor(line["amount_minor"], exchange_rate) for line in lines[:-1]]
        parts.append(expected - sum(parts))
        _require(all(expense[line["line_id"]]["debit_minor"] == value for line, value in zip(lines, parts)),
                 "invoice component journal mismatch")
        _require(credit["credit_minor"] == expected and credit["debit_minor"] == 0, "invoice payable mismatch")
        _require(all(r["entity_id"] == invoice["entity_id"] and r["rate_id"] == rate_id for r in rows),
                 "invoice journal entity/rate mismatch")
        periods = {r["reporting_period"] for r in rows}
        _require(len(periods) == 1, "inconsistent invoice reporting periods")
        if _time(invoice["issued_at"]).strftime("%Y-%m") not in periods:
            add("reporting_period", [iid], expected, "KZT", [invoice["doc_id"], credit["row_id"]])

    for group in obligations.values():
        _require(len(group) <= 2, "unsupported duplicate cardinality")
        if len(group) == 2:
            a, b = group
            _require(a["total_minor"] == b["total_minor"] and a["currency"] == b["currency"],
                     "ambiguous duplicate obligation")
            add("duplicate_invoice", [a["invoice_id"], b["invoice_id"]], a["total_minor"], a["currency"],
                [a["doc_id"], b["doc_id"], credits[a["invoice_id"]]["row_id"],
                 credits[b["invoice_id"]]["row_id"]])

    for payment in payments:
        pid, amount = payment["payment_id"], payment["amount_minor"]
        target = inv[payment["remittance_invoice_id"]]
        _require(type(amount) is int and amount > 0 and payment["currency"] == target["currency"],
                 "invalid payment amount/currency")
        rows = payment_rows[pid]
        debits = [r for r in rows if r["account"] == "payable"]
        credits_bank = [r for r in rows if r["account"] == "bank"]
        _require(len(rows) == 2 and len(debits) == len(credits_bank) == 1, "payment journal incomplete")
        debit, bank = debits[0], credits_bank[0]
        _require(debit["debit_minor"] == bank["credit_minor"] and
                 debit["credit_minor"] == bank["debit_minor"] == 0, "payment journal not balanced")
        _require(all(r["entity_id"] == target["entity_id"] and
                     r["invoice_id"] == target["invoice_id"] for r in rows), "payment journal scope mismatch")
        correct_rate, correct_id = quote(payment["currency"], payment["timestamp"])
        used_id = debit["rate_id"]
        _require(bank["rate_id"] == used_id, "mixed payment rate IDs")
        used_rate = "1" if used_id is None else rates_by_id[used_id]["rate"]
        _require(debit["debit_minor"] == _round_minor(amount, used_rate),
                 "payment posting does not match recorded rate")
        expected = _round_minor(amount, correct_rate)
        difference = abs(expected - debit["debit_minor"])
        docs = [target["doc_id"], payment["doc_id"], debit["row_id"], bank["row_id"]]
        if correct_id is not None:
            docs.append(correct_id)
        if difference or used_id != correct_id:
            add("fx_rate_or_date", [pid, debit["row_id"]], difference, "KZT", docs)
        references = payment["invoice_refs"]
        _require(type(references) is list and
                 all(type(ref["amount_minor"]) is int and ref["amount_minor"] > 0 and
                     ref["invoice_id"] in inv for ref in references), "invalid payment reference")
        _require(sum(ref["amount_minor"] for ref in references) <= amount, "allocation exceeds payment")
        correctly_applied = sum(ref["amount_minor"] for ref in references
                                if ref["invoice_id"] == target["invoice_id"])
        if correctly_applied != amount:
            other_docs = [inv[ref["invoice_id"]]["doc_id"] for ref in references
                          if ref["invoice_id"] != target["invoice_id"]]
            add("payment_allocation", [target["invoice_id"], pid],
                _round_minor(amount - correctly_applied, correct_rate), "KZT", docs + other_docs)

    return {"issues": sorted(signatures), "evidence": evidence,
            "checked_postings": len(ledger), "checked_documents": len(invoices) + len(payments)}
