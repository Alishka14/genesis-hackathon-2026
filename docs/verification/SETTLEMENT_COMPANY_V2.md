# LG-023 — Versioned LedgerWorld settlement episodes (split payments + supplier refunds)

**Status:** review candidate. **Scope:** the original `company_settlements` route remains **clean-only**; the opt-in `company_settlement_fault` route now supports controlled v2 duplicate/allocation/compound counterpairs with exactly the same public policy/schema. See [V2_CAUSAL_PAIRS.md](V2_CAUSAL_PAIRS.md). No changes to v1 fault generation, closed truth scoring or official reward. A passing internal suite is not an organizer D01–D20 certification.

## Why v2 is necessary
The existing `accrual_company_v1` requires each ordinary payment to be linked in full to one `remittance_invoice_id`, with two ledger postings associated with that invoice. That constraint cannot represent a legitimate split payment or vendor refund without inventing a `payment_allocation` fault or changing historical accounting semantics. `accrual_company_v2` is explicitly versioned and **opt-in** via the new scenario `company_settlements`.

## User-visible contract

    from ledgergym.generator import generate_episode
    public, truth = generate_episode(81, {
        "scenario": "company_settlements",
        "postings": 400,
        "documents": 80
    })

`public["manifest"]["schema_version"] = "0.4-company-settlements"` and `public["policy"]["accounting_model"] = "accrual_company_v2"`. The six files remain unchanged: `manifest.json`, `policy.json`, `ledger.csv`, `invoices.jsonl`, `payments.jsonl`, `fx.csv`. Public payments gain `kind` ("payment" or "refund"), `entity_id` and, for refunds only, `original_payment_id`. A legitimate split payment also publishes its `allocation_basis` (vendor remittance schedule), separate from actually applied `invoice_refs`, in both clean and faulty episodes. `remittance_invoice_id` is explicitly null when one transfer allocates across multiple invoices or when it is a refund. All original document and ledger IDs are preserved.

**New public policy rules:**
- `allocation_rule = explicit_same_currency_invoice_refs`: each positive payment is completely allocated through documentary `invoice_refs`; invoice amount remains in its native currency.
- `payment_journal_basis = vendor_ap_control`: vendor-level payable debit + bank credit for each positive transfer. For a split, both posted rows have null `invoice_id`; invoice-level allocation is proven by the payment document.
- `refund_rule = linked_after_all_positive_payments`: refund documents must reference an existing original positive payment, the same entity/currency and explicit invoice shares **actually paid by that original transfer**. Refunds must follow the last ordinary transfer.
- `refund_currency = KZT`: this version deliberately avoids unsupported FX differences on a returned transfer; ordinary USD and KZT invoices/payments still work under the original published FX rule.
- `refund_invoice_effect = restore_outstanding`: bank debit + payable credit reverse the applied cash; they are not a credit note or invoice cancellation.
- `accounting_model = accrual_company_v2`: older v1 definitions and validator remain unchanged.

All amount fields are integer minor units. FX rates remain decimal strings; KZT postings use half-even rounding. The v2 validator derives ledger correctness and balances from **public documents and FX quotations** using `fractions.Fraction` rather than consuming private labels or importing generator calculations.

## Files and integration
- `ledgergym/company_world_v2.py`: deterministic new episode generator. Starts from a valid clean v1 company with requested 200–2000 postings and 20–200 documents; converts a KZT payment to a two-invoice split, and a *different existing payment document* into a later documented supplier refund of an original KZT payment. This preserves document/row counts exactly.
- `ledgergym/company_checks_v2.py`: public-only independent validation of invoice/journal entries, FX, splits, original-payment refund links, over-allocations, period boundaries, bank funding, net invoice balances. Rejects inconsistent stories even if globally balanced.
- `ledgergym/generator.py`: explicit `scenario="company_settlements"` route, rejects any requested fault/compound switches rather than silently changing labels.
- `ledgergym/episode_io.py`: v2 validator and matching private provenance requirements before export.
- `judge_adapter.py`: allows six-file export of the versioned scenario; trusted `JudgeEnv` uses unchanged transport and private scorer.
- `tests/test_company_settlements_v2.py`: seed/dimension matrix, direct v2 independent verifier vs `apply_refunds`, equality and evidence retrieval, six-file roundtrip, closed judge scoring, malformed finance and forged truth rejection, v1 compatibility.

### Run

    python -m pytest -q tests/test_company_settlements_v2.py
    python -m pytest -q -rs

Example standalone export:

    python -c "from ledgergym.company_world_v2 import build_settlement_company; from ledgergym.episode_io import export_episode; p,t,q=build_settlement_company(81,{'postings':400,'documents':80}); export_episode('settlement-episode',p,t,seed=81,provenance=q)"

Or use `judge_adapter.generate_episode(81, {"scenario":"company_settlements", "postings":400, "documents":80}, "new-episode-directory")`. The directory must not exist or must be empty. `private/truth.json` is `{"issues":[]}`; `private/provenance.json` records synthetic clean-case provenance, never supplied to an untrusted policy.

## What is and is not claimed
- **Real integration:** six public files; balance-preserving ledger rows; read-only tools can retrieve refund and split documents; clean evaluator has no false issue; independent preflight rejects inconsistent financial facts.
- **Not yet implemented:** v2 FX/cutoff fault injection, interleaved refund/positive-payment timing, multi-currency *cross*-allocation, cancellation/credit-note accounting, netting without provenance, general bank reconciliation or ledger controls beyond the synthetic policy. The sibling v2 fault route now supports duplicate, partial split allocation and their compound. A refund's original cash transaction is still identifiable from public records.
- The legacy `company` scenario retains all four independent faults and two compound scenarios under `accrual_company_v1`. V2 clean and v2 faulty variants share the same public `accounting_model` and six-file schema; neither replaces the legacy coverage.
- A refund-containing public company is inherently different from one where negative-value transfers are simply inserted without source evidence. Negative transfers and arbitrary bank credits remain unsupported.
- Public/private directories alone do not establish OS isolation; the existing isolated Docker runner remains the expected way to run untrusted agents.
- Submit/merge/publication and policy v2 production adoption require owner review; **do not** treat a green CI run as approval. GitHub CI for the stacked v2 benchmark branches has recently failed before job steps without logs; re-run tests locally or after the runner recovers.

**Review requests:** accounting treatment of return of vendor funds, documental completeness of `original_payment_id` and `invoice_refs`, versioned schema compatibility, and how to add v2 faulty counterparts without shortcut correlations.
