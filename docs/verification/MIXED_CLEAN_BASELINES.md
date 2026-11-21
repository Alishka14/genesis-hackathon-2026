# LG-024 — mixed train/dev benchmark for clean split/refund hard negatives

**Status:** implementation candidate; needs CI and owner review. All data are synthetic. These results are from open development episodes, **not** organizer-hidden GENESIS evaluations.

## Objective

Measure false allegations by four existing baseline policies when an episode includes *legal but misleading* financial signals: same-valued invoices for distinct services, a split payment allocated to two legitimate invoices, and a documented supplier refund. These are the genuine six-file `accrual_company_v2` episodes from LG-023, not the earlier standalone toy fixtures.

The old default dataset and generator stay unchanged. The new dataset format is opt-in via an explicit CLI flag; no v2 faults are silently asserted or invented.

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
| **v2 clean** | **2** | Full six-file split allocations and supplier refunds |
| **Total** | **10** | 8 v1 + 2 v2 |

Generator seeds for the 20 episodes are unique and stored only in private provenance. `index.json` contains opaque episode IDs and relative paths, not fault flags, secrets, seeds or private issue labels. Train/dev do not overlap.

In this **opt-in** design, the former additional four-single-fault mix and one redundant v1 clean slot are replaced with two v2 clean slots; all four singleton families, both compound types and a maximal 12-issue case remain covered.

## Evaluated policies

1. `seeded_random` — deliberately naive single suspicion;
2. `reconciliation` — reads public evidence, checks the published financial model and reports independently detected discrepancies; for clean-only `accrual_company_v2`, runs `validate_settlement_company` on observed **public tables** and submits no findings only after validation passes;
3. `mark_all` — deliberately accuses many invoices and exposes false positives;
4. `oracle` — evaluator-only perfect reference, **not** a policy available to an untrusted agent; no policy trajectory.

All non-oracle policies use the existing 100-action read-only `LedgerSandbox` path; `fixture_evaluation` replays their portable action sequences and checks identical score results.

Scoring remains `clip(2*F1 - 1 - 0.002*inspection_steps, -1, 1)`, unchanged. Matcher uses the same `accessible_evidence_ids` as the canonical evaluator, so a foreign key (`entity_id`) is not admitted as a standalone accessible evidence record.

## Additional comparison metrics

`summary.json` contains its historical per-policy `tp/fp/fn/mean_f1/mean_reward/mean_inspection_steps` entries **plus**, in this opt-in mode:

- `model_counts[split][accounting_model]`
- `clean_false_accusations[scope][accounting_model][policy]`, where `scope` = `train`, `dev` or `overall`.
- Each clean slice reports `episodes`, `false_accusation_episodes`, `fp`, `false_accusation_rate` (clean episodes with `FP > 0` divided by clean episodes), `mean_f1` and `mean_reward`.

**Shortcut risk (explicit):** In this open development collection every v2 episode is clean, and the accounting model version is visible in the public `policy.json`. An agent can simply learn that `accrual_company_v2` implies empty findings. This is an intentionally scoped **false-accusation diagnostic slice**, not a label-balanced hidden benchmark or a reliable estimate of generalization. A future rigorous benchmark needs v2 fault-injected paired controls before using v2 for held-out performance claims. The extended summary also includes `shortcut_warning`.

**Interpretation:** These are *measured baseline errors on synthetic clean cases*, not a learned-agent result or a measure of real-world auditor accuracy. `mark_all` and `seeded_random` intentionally over-accuse. `reconciliation` contains model-specific code and should **not** be presented as generalizable AI performance. A zero false-allegation rate on four open clean v2 episodes does not establish robustness on novel faults or withheld companies.

`trajectories.jsonl` contains only non-oracle public interactions; private truth, provenance, private seeds and issue IDs never appear in those action logs. The trusted evaluator reads private truth only to compute aggregate scores.

## Regression and security gates

    python -m pytest tests/test_settlement_dataset_benchmark.py -q
    python -m pytest -q -rs -p no:cacheprovider

Checks: disjoint and byte-identical 10+10 datasets, unique private seeds, v1 and v2 proportions, all official fault families and compound types, 60/60 replay, four baseline false-positive counts, clean F1/reward expectations, absence of hidden values in public trajectories, valid CLI exports and rejection of deliberately corrupted v2 allocations. Existing default dataset tests must still pass.

The private/public directory split is **not itself a security boundary**; do not mount the dataset root (which also contains private files) into an untrusted agent container. Existing Docker isolation and the closed official judge remain separate components.

## Remaining work / non-goals

- This extension does **not** make v2 generate faults or compound scenarios. All positive truth currently comes from v1.
- It does not assess actual RL training, deployed LLM performance or real financial audits.
- No cross-currency invoice allocations, refund/credit-note netting, partial interleaved settlements or auditor-grounded accounting compliance are claimed.
- The real organizer D01–D20 financial checks and hidden policy episodes have not been seen.
- Before release: owner must approve integration of the stacked draft PRs #20 → #23 → #24 → #25 → LG-024, review policy v2, run official compliance checks and authorize the final merge. Do not treat a green CI as authorization.
