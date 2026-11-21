# LG-025 — Causal counterpairs for LedgerGym accrual_company_v2

**Status:** DRAFT / local development. Not an organizer-hidden test, not a validated trained-model result. **Source:** existing `accrual_company_v2` clean invoice/payment journals, `LedgerScore` 1:1 evidence matcher and public remittance documents.

## Objective and limitations

Previously all v2 episodes were clean, so an agent could shortcut by checking the public `accounting_model` rather than auditing financial documents. This change creates both **clean and intentionally faulty v2** episodes under the same `schema_version` and `policy.json` and verifies the pairwise change in evidence and expected findings.

The v1 generator with four official fault families and two compound scenarios is preserved. This branch implements v2 controls for **duplicate invoice** and **payment allocation**, including a linked compound; **v2 FX and reporting-cutoff fault injection are not implemented**. Existing v2 supplier refunds remain valid and documented in both clean and faulty cases.

## Public evidence and controlled changes

All clean/fault variants have identical manifest, policy, opaque IDs, base ledger, FX quotes and episode ID when using the same seed. Deliberate changes are limited to financial facts that determine the error:

| Mode | Controlled public delta | Ground truth and evidence |
| --- | --- | --- |
| `duplicate_invoice` | Second invoice's service reference is made equal to the first despite the same vendor and face value | Both invoices + two related payable postings |
| `payment_allocation` | One applied split `invoice_refs` allocation reduced by one minor unit against the vendor's documented `allocation_basis` | Payment document containing **both** basis and applied allocations + both invoice documents + payable posting |
| `duplicate_allocation` | Both changes above, to a shared split-related pair of invoices | Two distinct truth issues, with separate evidence chains, tied through one split payment |

`allocation_basis` is a **public remittance instruction** published on the split document in *both* clean and faulty episodes, never an error flag. The difference between intended remittance and actual application is therefore independently verifiable. On a clean split these values are identical. There is no `truth`, `issue_id`, `provenance`, `fault_mode` or benchmark pair label in public files.

**V2 scorer compatibility:** exact `type`, affected IDs, KZT amount and sufficient public evidence sets; one-to-one matching and the official reward remain unchanged.

**Security:** the private `truth.json` and `provenance.json` are evaluator-side. The stored pair manifest and its clean/fault mapping are **private research data**. Do not mount a dataset root containing private files into an untrusted agent. Only expose one public folder at a time through the established restricted judge protocol.

## Public-only verification

`ledgergym.settlement_faults_v2.inspect_settlement_faults(public)` derives findings from public documents without importing a generator or reading private truth:

1. Detect duplicate service obligations by vendor, service reference, currency and amount.
2. Detect single-invoice short allocation by comparing a documented split basis with the actual applied `invoice_refs`.
3. Reverse **only** the recognized discrepancies in a private in-memory copy and call the existing independent v2 validator to check every other financial invariant (cash/AP balance, invoice lines, exchange rates, refund original link, period, capital, evidence accessibility).
4. Reject unexpected corruptions, ambiguous multi-invoice differences and unsupported financial phenomena rather than inventing ground truth.

The original public data is not mutated by the audit. `validate_settlement_episode(public, truth)` matches the independently derived issue signatures and requires each truth issue to provide a complete public evidence chain. This is a deterministic synthetic-policy oracle; it does **not** certify real-world accounting accuracy.

## Generator and judge integration

    from ledgergym.generator import generate_episode

    public, truth = generate_episode(81, {
        "scenario": "company_settlement_fault",
        "postings": 400,
        "documents": 80,
        "fault": "payment_allocation"
    })

Existing clean route: `scenario="company_settlements"`. Both expose `accounting_model="accrual_company_v2"` and `schema_version="0.4-company-settlements"`.

`judge_adapter.generate_episode(...)` supports the new route, writes the six public files plus private truth/provenance, and uses the unchanged canonical scorer. `reconciliation` baseline calls the **public-only inspector**, never a truth parameter, so a fault must be supported by observable facts.

### Paired dataset and four baseline policies

    python -m ledgergym.v2_pair_dataset ./new-pairs --seed 2026 --evaluate

Generates six **disjoint** causal pairs: one `duplicate_invoice`, one `payment_allocation` and one compound per split (`train` and `dev`). Each pair contains two variants with neutral names `variant-a`/`variant-b`, where clean-vs-fault mapping and shared seed are stored in `private_pair_index.json` **outside the public episode directories**. There are 12 total exported episodes. Pairs share a seed but different pair seeds are unique.

`evaluation/summary.json` compares seeded-random, reconciliation, mark-all and evaluator-only oracle on clean and faulty variants. The `paired_accuracy` metric is the proportion of pairs where a policy both avoids false accusations in clean and correctly handles every issue in faulty.

The standard `ledgergym.company_dataset` opt-in mode also now gives **one clean and one faulty v2** company in each 10-episode train/dev split (plus 8 v1 including four singleton types, both v1 compounds, a v1 clean case and a 12-issue stress). Train v2 fault is allocation, dev v2 fault is duplicate. Thus a visible v2 model **no longer guarantees empty truth**. The sample is small and type scheduling is predictable: it is still **not** a secret balanced generalization benchmark.

## Tests and known limitations

    python -m pytest -q tests/test_v2_causal_pairs.py tests/test_v2_pair_dataset.py
    python -m pytest -q tests/test_settlement_dataset_benchmark.py
    python -m pytest -q -rs -p no:cacheprovider

Tests cover same-seed clean/fault reconstruction of every changed field, three modes, three seeds, three dataset sizes, evidence accessibility, truth consistency, canonical judge accepted findings, deterministic replay/scoring, clean false allegations, private pair-index separation, all four baseline policies and six paired train/dev controls.

**Still open:** production review of `allocation_basis` public contract, independent finance expert review of the synthetic policy and documents, v2 FX/cutoff faults, expanded counterfactual permutations, hidden organizer compliance checks and actual AI/LLM policy evaluation. No code is automatically merged or submitted.
