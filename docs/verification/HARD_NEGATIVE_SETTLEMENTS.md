# LG-022 — Clean Hard Negative Settlement Fixtures

**Status:** TESTED ONLY AFTER CI; currently an engineering review candidate. These are **standalone internal reconciliation fixtures, NOT six-file official company episodes**. No official `truth` files or private evaluator outputs are exposed by these functions.

## Why this extension exists
A financial auditor should not infer fraud merely from matching invoice amounts, multiple partial payments, a split allocation, a supplier refund, or similar numbers in different currencies.

The current `accrual_company_v1` generator has an intentional one-remittance-invoice-per-payment policy, so real `payments.jsonl` cannot yet represent all these clean cases without a versioned public-contract change. This feature adds **conservative self-contained settlement validation** without modifying that policy or the official score.

## Included cases
`ledgergym.hard_negative_cases.make_hard_negative_case(seed, kind)` accepts:

| Kind | Financial event | Expected accounting outcome |
| --- | --- | --- |
| `equal_values_distinct_services` | Two same-amount invoices from one vendor but different economic services | Both obligations valid, zero duplicate faults |
| `split_payment` | One positive payment explicitly split across two invoices | 9,000 + 6,000 KZT minor units paid |
| `multiple_partial_payments` | Two partial payments against one invoice | Paid 7,000; 3,000 remaining |
| `partial_refund` | Supplier returns part of an already applied payment | Paid balance reduced to 7,000 |
| `split_with_refund` | Refund from an earlier split payment, attributed separately to two invoices | Net paid 6,000 and 5,000 |
| `parallel_currencies` | Equal numerical amounts, one in USD and one in KZT, separately paid | Currency buckets never summed without conversion |

**These are intentionally clean**: a simple pattern-matching auditor falsely calling both same-amount invoices duplicates must receive FP. Test `test_equal_invoice_amount_is_not_evidence_of_duplicate` checks this via existing official scorer, but it does not introduce a new ground-truth error type.

## Contract: `apply_refunds(invoices, payments, refunds)`
This operates on the existing *trusted internal* `allocate_payments` interface. Refund fields:

- `refund_id` (unique), `kind="refund"`
- `original_payment_id`: explicit existing payment reference
- `entity_id`, `currency`, `timestamp` with timezone offset
- `amount_minor`: positive integer minor units
- `invoice_refs`: positive per-invoice allocations, summing exactly to refund amount

The function first requires all ordinary transfers to be fully allocated by documentary references. All refund timestamps must be strictly later than **every** ordinary payment timestamp, avoiding undefined interleaving semantics. Every refund references only invoices actually paid by the original transfer and must use exactly its entity and currency. Across refunds, the cumulative amount for a (payment,invoice) pair cannot exceed the original allocation. Invalid batches fail atomically: no guessing by ID, time or amount, and no silent partial application.

Result: original positive transfer allocations, explicit refunds and **net paid/outstanding** amounts for each invoice. Refunds never change the original paid transfer amount, and currencies are tracked separately. The underlying invoice remains due after supplier remits money back; these are not credit notes or invoice cancellations.

### Deliberate nonfeatures and limits
- No change to `LedgerWorld`, `LedgerFault`, `company_checks`, `policy.json`, `truth.json`, private provenance, official sandbox or reward.
- No public six-file serialization, reference FX conversion, cancellation/credit-note semantics, cross-currency refunds, refund-before-payment interleaving or balances after late positive remittances.
- No new official train/dev episodes are emitted by these fixtures. This module **does not close** the production clean-refund/split requirement and must not be shown as an end-to-end company scenario.
- Any eventual production integration should propose a versioned `allocation_rule` and journal model, ensure the official tools can retrieve refund evidence and apply independent preflight checks. Such a change needs owner review before merging.

## Verification
From repository root:

    python -m pytest -q tests/test_hard_negative_settlements.py
    python -m pytest -q -rs

Tests cover conservation of paid/unpaid amounts by currency, six varieties × three seeds, order and ID robustness, duplicate original claims, wrong sources, currency/entity mismatch, timestamp ordering, zero/negative/bool/float amounts, malformed references, and an actual clean company pair with identical vendor/currency/amount but different service identities.

**Scope:** human financial review still required. D01–D20 (hidden organizer checks) are not available; a passing local suite is not official certification.
