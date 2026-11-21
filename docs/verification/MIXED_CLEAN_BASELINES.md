# LG-024/LG-025 — mixed train/dev benchmark for v2 clean and faulty split/refund episodes

**Status:** implementation candidate; needs CI and owner review. All data are synthetic. These results are from open development episodes, **not** organizer-hidden GENESIS evaluations.

## Objective

Measure false allegations by four existing baseline policies when an episode includes *legal but misleading* financial signals: same-valued invoices for distinct services, a split payment allocated to two legitimate invoices, and a documented supplier refund. These are the genuine six-file `accrual_company_v2` episodes from LG-023, not the earlier standalone toy fixtures.

The old default dataset and generator stay unchanged. The opt-in profile now includes one *clean* and one **evidence-backed faulty** v2 episode in each split. v2 still preserves the same public policy/schema across both outcomes.

## One-command generation and evaluation

    python -m ledgergym.company_dataset ./ledgergym-dev-set --seed 2026 --settlement-hard-negatives --evaluate

Creates a **new** `ledgergym-dev-set/` folder: exactly ten `train` and ten `dev` episodes, six public and two private files each, plus `index.json`, `evaluation/summary.json` and `evaluation/trajectories.jsonl`.

Internally:

    from ledgergym.company_dataset import create_company_dataset
    from ledgergym.fixture_evaluation import evaluate_fixture_dataset
    index = create_company_dataset(
        "./fresh-data", seed=2026, include_settlement_hard_negatives=True)
    report = evaluate_fixture_dataset("./fresh-data", "./fresh-report")

Without the flag, legacy `create_company_dataset(root, seed=...)` and its index kind, plan distribution and outputs remain unchanged. The extension has the explicit kind `synthetic_company_development_with_settlements`.

### Distribution per split

| Model / scenario | Episodes | Purpose |
| --- | ---: | --- |
| v1 clean | 1 | Conventional same-amount obligations that remain valid |
| v1 singleton faults (4 families) | 4 | Duplicate, allocation, FX/date, period cutoff |
| v1 compounds | 2 | FX+allocation, duplicate+allocation |
| v1 stress (12 issues) | 1 | Check scoring and investigative step budgets |
| **v2 clean** | **1** | Legitimate split payment and supplier refund |\n| **v2 faulty** | **1** | Same v2 model with a documented allocation or duplicate obligation fault |
| **Total** | **10** | 8 v1 + 2 v2 |

Generator seeds for the 20 episodes are unique and stored only in private provenance. `index.json` contains opaque episode IDs and relative paths, not fault flags, secrets, seeds or private issue labels. Train/dev do not overlap.

The v2 faulty episode uses a payment-allocation fault in train and a duplicate-invoice fault in dev; both are resolved from public evidence. All four v1 singleton families, both compound types and a 12-issue case remain covered. See [V2_CAUSAL_PAIRS.md](V2_CAUSAL_PAIRS.md) for same-seed clean/fault pairs and the compound v2 counterpart.

## Evaluated policies

1. `seeded_random` — deliberately naive single suspicion;
2. `reconciliation` — reads public evidence, checks the published financial model and reports independently detected discrepancies; on `accrual_company_v2`, uses public `allocation_basis` and applied `invoice_refs` alongside the service identity and audited journal. It submits no findings only when the public-only inspection finds none;
3. `mark_all` — deliberately accuses many invoices and exposes false positives;
4. `oracle` — evaluator-only perfect reference, **not** a policy available to an untrusted agent; no policy trajectory.

All non-oracle policies use the existing 100-action read-only `LedgerSandbox` path; `fixture_evaluation` replays their portable action sequences and checks identical score results.

Scoring remains `clip(2*F1 - 1 - 0.002*inspection_steps, -1, 1)`, unchanged. Matcher uses the same `accessible_evidence_ids` as the canonical evaluator, so a foreign key (`entity_id`) is not admitted as a standalone accessible evidence record.

## Additional comparison metrics

`summary.json` contains its historical per-policy `tp/fp/fn/mean_f1/mean_reward/mean_inspection_steps` entries **plus**, in this opt-in mode:

- `model_counts[split][accounting_model]`\n- `v2_label_counts[split]`: one clean and one faulty v2 episode per split
- `clean_false_accusations[scope][accounting_model][policy]`, where `scope` = `train`, `dev` or `overall`.
- Each clean slice reports `episodes`, `false_accusation_episodes`, `fp`, `false_accusation_rate` (clean episodes with `FP > 0` divided by clean episodes), `mean_f1` and `mean_reward`.

**Shortcut risk (explicit):** Both clean and faulty episodes now use the **same** visible `accounting_model`, so the previous shortcut that v2 always means empty truth is removed. However, only two v2 cases per split and their fixed train/dev fault modes make this an **open diagnostic sample**, not a reliable estimate of generalization. The report retains a `shortcut_warning`. A separate six-pair dataset provides same-seed causal controls, not a hidden benchmark.

**Interpretation:** These are *measured baseline errors on synthetic clean cases*, not a learned-agent result or a measure of real-world auditor accuracy. `mark_all` and `seeded_random` intentionally over-accuse. `reconciliation` contains model-specific code and should **not** be presented as generalizable AI performance. A zero false-allegation rate on two open clean v2 episodes does not establish robustness on novel faults or withheld companies.

`trajectories.jsonl` contains only non-oracle public interactions; private truth, provenance, private seeds and issue IDs never appear in those action logs. The trusted evaluator reads private truth only to compute aggregate scores.

## Regression and security gates

    python -m pytest tests/test_settlement_dataset_benchmark.py -q
    python -m pytest -q -rs -p no:cacheprovider

Checks: disjoint and byte-identical 10+10 datasets, unique private seeds, v1 and v2 proportions, all official fault families and compound types, 60/60 replay, four baseline false-positive counts, clean F1/reward expectations, absence of hidden values in public trajectories, valid CLI exports and rejection of deliberately corrupted v2 allocations. Existing default dataset tests must still pass.

The private/public directory split is **not itself a security boundary**; do not mount the dataset root (which also contains private files) into an untrusted agent container. Existing Docker isolation and the closed official judge remain separate components.

## Remaining work / non-goals

- V2 now supports controlled duplicate-invoice and split-allocation faults plus their coupled compound **in a separate fault route**; v2 FX and cutoff faults remain unimplemented. The original v1 continues to provide all four official fault families and two compounds.
- It does not assess actual RL training, deployed LLM performance or real financial audits.
- No cross-currency invoice allocations, refund/credit-note netting, partial interleaved settlements or auditor-grounded accounting compliance are claimed.
- The real organizer D01–D20 financial checks and hidden policy episodes have not been seen.
- Before release: owner must approve integration of the stacked draft PRs #20 → #23 → #24 → #25 → #26 → #27, review policy v2, run official compliance checks and authorize the final merge. Do not treat a green CI as authorization.
