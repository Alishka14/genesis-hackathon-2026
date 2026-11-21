"""Hand-calculated external-to-generator reference cases for the second auditor.

The values, postings and truth are manually specified in this file. No calls
to company_world, production company_checks, baselines or score are used.
"""
import copy
import pytest

from ledgergym.independent_finance_audit import audit_company


def _manual():
    event = "2026-01-31T23:30:00+00:00"  # 2026-02-01 04:30 +05
    def row(identifier, account, dr, cr, iid=None, pid=None,
            line=None, rate="rate-current"):
        return {"row_id": identifier, "timestamp": event, "account": account,
                "debit_minor": dr, "credit_minor": cr, "currency": "KZT",
                "entity_id": "supplier", "invoice_id": iid, "payment_id": pid,
                "line_id": line, "rate_id": rate, "reporting_period": "2026-02"}
    capital1 = row("opening-bank", "bank", 1000, 0, rate=None)
    capital2 = row("opening-equity", "equity", 0, 1000, rate=None)
    for capital in (capital1, capital2):
        capital["entity_id"] = "company"
        capital["timestamp"] = "2026-02-01T00:00:00+05:00"
    ledger = [capital1, capital2,
              row("expense-one", "expense", 2, 0, "invoice", line="line-one"),
              row("expense-two", "expense", 150, 0, "invoice", line="line-two"),
              row("invoice-payable", "payable", 0, 152, "invoice"),
              row("payment-payable", "payable", 76, 0, "invoice", "payment"),
              row("payment-bank", "bank", 0, 76, "invoice", "payment")]
    tables = {
        "invoices": [{
            "invoice_id": "invoice", "doc_id": "invoice-doc",
            "entity_id": "supplier", "issued_at": event,
            "due_at": "2026-02-15T00:00:00+05:00", "currency": "USD",
            "total_minor": 101,
            "line_items": [
                {"line_id": "line-one", "service_ref": "service",
                 "amount_minor": 1, "description": "S1"},
                {"line_id": "line-two", "service_ref": "service",
                 "amount_minor": 100, "description": "S2"},
            ],
        }],
        "payments": [{
            "payment_id": "payment", "doc_id": "payment-doc",
            "timestamp": event, "currency": "USD", "amount_minor": 51,
            "remittance_invoice_id": "invoice",
            "invoice_refs": [{"invoice_id": "invoice", "amount_minor": 51}],
        }],
        "ledger": ledger,
        "fx": [
            {"rate_id": "rate-previous", "date": "2026-01-31",
             "source_currency": "USD", "target_currency": "KZT", "rate": "1.25"},
            {"rate_id": "rate-current", "date": "2026-02-01",
             "source_currency": "USD", "target_currency": "KZT", "rate": "1.50"},
        ],
    }
    public = {
        "manifest": {
            "schema_version": "0.3-company", "episode_id": "manual",
            "company_id": "company", "base_currency": "KZT",
            "period_start": "2026-02-01T00:00:00+05:00",
            "period_end": "2026-02-28T23:59:59+05:00",
            "timezone": "+05:00", "rounding": "ROUND_HALF_EVEN",
            "counts": {name: len(rows) for name, rows in tables.items()},
        },
        "policy": {
            "accounting_model": "accrual_company_v1",
            "rounding": "ROUND_HALF_EVEN",
            "currency_exponents": {"KZT": 2, "USD": 2},
            "fx_date": "local_transaction_date",
            "cutoff_timezone": "+05:00",
            "period_rule": "calendar_month_of_transaction",
            "invoice_rounding": "round_total_residual_to_last_line",
            "duplicate_rule": "one_invoice_per_service_ref",
            "allocation_rule": "allocate_full_payment_to_remittance_invoice",
            "allocation_claim_currency": "KZT",
        }, "tables": tables,
    }
    return public


def _truth(*issues):
    return {"issues": [{
        "issue_id": f"private-manual-{number}",
        "type": kind, "affected_ids": affected,
        "expected_amount_minor": amount, "currency": "KZT",
        "allowed_evidence_sets": [evidence],
    } for number, (kind, affected, amount, evidence) in enumerate(issues)]}


@pytest.mark.parametrize("mode", ["clean", "wrong_fx", "wrong_period",
                                   "bad_allocation", "fx_allocation"])
def test_manually_derived_company_faults(mode):
    public = _manual()
    truth = _truth()
    fx = ("fx_rate_or_date", ["payment", "payment-payable"], 12,
          ["invoice-doc", "payment-doc", "payment-payable", "payment-bank",
           "rate-current"])
    allocation = ("payment_allocation", ["invoice", "payment"], 39,
                  ["invoice-doc", "payment-doc", "payment-payable",
                   "payment-bank", "rate-current"])
    period = ("reporting_period", ["invoice"], 152,
              ["invoice-doc", "invoice-payable"])
    if mode in ("wrong_fx", "fx_allocation"):
        for row in public["tables"]["ledger"]:
            if row["payment_id"] == "payment":
                row["rate_id"] = "rate-previous"
                if row["debit_minor"]:
                    row["debit_minor"] = 64  # 51 × 1.25 = 63.75 => 64
                else:
                    row["credit_minor"] = 64
    if mode in ("bad_allocation", "fx_allocation"):
        public["tables"]["payments"][0]["invoice_refs"][0]["amount_minor"] = 25
    if mode == "wrong_period":
        for row in public["tables"]["ledger"]:
            if row["invoice_id"] == "invoice" and row["payment_id"] is None:
                row["reporting_period"] = "2026-01"
    if mode == "wrong_fx":
        truth = _truth(fx)
    if mode == "wrong_period":
        truth = _truth(period)
    if mode == "bad_allocation":
        truth = _truth(allocation)
    if mode == "fx_allocation":
        truth = _truth(fx, allocation)
    result = audit_company(public, truth)
    assert result["status"] == "PASS"
    assert result["issues_audited"] == len(truth["issues"])
    assert result["journal_net_minor"] == 0


def test_manually_derived_audit_rejects_wrong_money_and_forged_evidence():
    public = _manual()
    bad = copy.deepcopy(public)
    bad["tables"]["ledger"][2]["debit_minor"] += 1
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(bad, _truth())
    bad = _manual()
    bad["tables"]["payments"][0]["invoice_refs"][0]["amount_minor"] = 25
    forged = _truth(("payment_allocation", ["invoice", "payment"], 38,
                     ["invoice-doc", "payment-doc", "rate-current"]))
    with pytest.raises(ValueError, match="independent audit"):
        audit_company(bad, forged)
