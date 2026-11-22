# LedgerGym — Design Note (release, 22.11.2026)

**Status:** describes the release candidate in `main` on 22.11.2026. Official submission has not been independently confirmed; local and GitHub CI verification are not organizer certification.

## Purpose and scope

LedgerGym is a reproducible *synthetic* financial-audit environment for training/evaluating an evidence-aware decision policy. It generates ledger entries and documents from a consistent financial history, applies controlled fault interventions, exposes a small bounded tool API and evaluates submitted findings with explicit evidence requirements. It is **not** an ERP, a production accounting compliance engine, or a trained autonomous auditing model.

Public episode files: `ledger.csv`, `invoices.jsonl`, `payments.jsonl`, `fx.csv`, `policy.json`, `manifest.json`. Evaluator-only: `truth.json`, `provenance.json`, pair labels, and the oracle baseline. A dataset directory may contain both public and private files for local trusted research; the *agent container* must never receive the private portion.

## Core architecture

1. **Company generator** (`ledgergym/company_world.py` for v1 and `company_world_v2.py` for v2) builds balanced synthetic accrual/payment histories (200–2,000 postings; 20–200 documents). The canonical v1 model supports four fault families: `duplicate_invoice`, `payment_allocation`, `fx_rate_or_date`, `reporting_period`, plus `fx_allocation` and `duplicate_allocation` compound cases. Versioned v2 adds legitimate split payments/refunds; targeted v2 fault pairs currently cover duplicate invoices and allocations, **not all four fault families in v2**.
2. **Preflight** (`company_checks.py`, `company_checks_v2.py`, `settlement_faults_v2.py`) checks public financial invariants and whether submitted truth is supported by reachable evidence. The public inspector shares deterministic checks with the baseline; its excellent synthetic score should not be represented as independent generalization.
3. **Judge API** (`judge_adapter.py`, `ledgergym/canonical.py`) exposes reset/step, five canonical investigation actions including calculator/submit, closed/train reward visibility rules, bounded pagination, deadline and step budget. The older in-process `LedgerSandbox` is a trusted development interface and **not** an agent security boundary.
4. **Matcher/reward** (`ledgergym/score.py`) validates findings, computes one-to-one evidence-aware matching and scores TP/FP/FN/Precision/Recall/F1 and `reward = clip(2 × F1 − 1 − 0.002 × inspection_steps, −1, 1)`. Attempts to spam/guess findings cannot improve a correct score.
5. **Isolation** (`ledgergym/isolated_runner.py`) launches an untrusted policy under Docker with `--network none`, read-only root, non-root user, restricted capabilities/resources and only the policy script mounted. The evaluator and private data stay on the host. The Docker daemon and host remain the trusted computing base. Local tests do not replace an independent penetration test.
6. **Benchmark/replay** (`company_dataset.py`, `fixture_evaluation.py`, `v2_pair_dataset.py`) creates 10 train + 10 dev synthetic episodes, four controls (random, reconciliation, mark-all, evaluator-side oracle), 60 action replays, and six causal clean/fault pair comparisons. `flight_recorder.py` captures canonical transitions; the new `evaluation/trajectories_full.jsonl` captures full **trusted development** baseline transitions. It includes exposed development reward but **not** truth/provenance; do not put this file into an untrusted closed-mode agent's input.
7. **Presentation only** (`ledgergym/dashboard.py` and `ledgergym/dashboard_static/`) serves a read-only, localhost dashboard. It exposes only approved aggregate summary data and pages from each episode's `public/` directory. The UI never receives private evaluator truth; it is not remotely hosted. The `/api/findings` endpoint runs the existing public-rule deterministic reconciliation checker for the chosen episode and exposes claimed amounts, public affected IDs and supporting evidence IDs (not issue IDs, private truth or evaluator score). This is a reference inspector tied to the synthetic model, not an independently validated AI agent. The additional `/api/replay` endpoint serves only compact trusted-development event metadata (step, action kind, public table, record counts, termination flag, development reward) for non-oracle baselines, with an action-only fallback for older datasets. Do not expose this API as a closed-mode agent tool.

## Empirical evidence and limits

Measured on 22.11.2026 (details: README "Результаты", `docs/verification/P0_FULL_RUN_2026-11-22.md`):
- Automated tests on CPython 3.11 and 3.13 pass; the 14 Docker isolation tests pass separately with the pinned image (22/22 Docker-backed checks, 0 skipped). GitHub Actions: 3/3 jobs green.
- Full release gate `verify_p0_release.py --mode full`: 6/6 stages; installed-wheel offline gate with 175 tests.
- One-command check `scripts/verify_integration.py --mode focused` passes inside the pinned container with `--network none` and without Git.
- Four baselines (`ledgergym.agent_diagnostics`): on the open 10+10 set and on 30 held-out episodes with unseen seeds and parameter combinations, oracle and reconciliation reach P = R = F1 = 1 with no false accusation on clean episodes; seeded random and mark-all score F1 = 0 and return −1. Reconciliation shares modelling assumptions with the generator, so its score shows consistency of data and evaluator, not task difficulty.
- Paired invariance: permuting every table and bijectively renaming every ID (four ID formats) preserves the oracle answer and reward in 40/40 variants through `JudgeEnv` and `score_episode`.
- Data: reverting the field-level interventions recorded in `provenance.json` restores balanced books (debits = credits per currency; invoice and payment totals reconcile) in 40/40 episodes; all 280 truth evidence sets are reachable through the read tools.
- Declared amount tolerance: `AMOUNT_TOLERANCE_MINOR = 0` in `ledgergym/score.py` (exact integer minor units).

Known limitations: no externally validated financial corpus; KZT/USD and simplified accrual model (no taxes, no realised FX differences); v2 settlement scenarios cover duplicates and allocations only; no trained RL/LLM policy (optional per the case); dashboard is read-only and local; the Docker boundary has tests but no independent security audit; the jury's resource limits (2 CPU, 4 GB, 60 s/episode) are observed locally (peak RSS ≈ 0.2 GB), not enforced.

## Reproducibility and safe deployment

- Python >=3.11 for runtime; pinned CPython 3.11 environment for the offline bundle builder.
- Runtime and frontend use only Python standard library; browser assets are included in wheel/sdist as package data.
- The dashboard listens **only** on `127.0.0.1`. It should not be exposed to the public internet or treated as an authentication/security system.
- `verify_integration.py` and `verify_offline_release.py` write sanitized aggregate reports and do not claim official organizer certification.
- Hashes validate delivered bundle file contents, not author identity or full supply-chain provenance.

## Licence and disclosure

Own code: MIT (`LICENSE`). Third-party build/test components: `THIRD_PARTY_NOTICES.md`. AI assistance (OpenAI Codex, ChatGPT, Claude Code): `docs/PROVENANCE_AND_AI_DISCLOSURE.md`. All data is synthetic.
