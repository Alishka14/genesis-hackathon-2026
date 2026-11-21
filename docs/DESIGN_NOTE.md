# LedgerGym — Design Note (release candidate, 21.11.2026)

**Status:** draft for team and finance-case review, not an approved competition certification. Implementation resides in stacked draft GitHub PRs; no automatic merge/publication/submission. This note describes the architecture actually present in the branch and identifies independent review requirements.

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
7. **Presentation only** (`ledgergym/dashboard.py` and `ledgergym/dashboard_static/`) serves a read-only, localhost dashboard. It exposes only approved aggregate summary data and pages from each episode's `public/` directory. The UI never receives private evaluator truth; it is not remotely hosted.

## Empirical evidence and limits

The operator confirmed on the preceding branches:
- Full integration gate on macOS, Python 3.14.0: all local stages passed.
- Real pinned-Docker tests on Apple Silicon: 22 passed, 0 failed/skipped.
- Local installed-wheel offline gate, Python 3.11.18: nine stages passed, 45/45 installed package tests passed; 145 bundle files validated by SHA-256, 60 replays.
- Development benchmark using mixed 10+10, four baselines: reconciliation TP=42/42, FP=0, FN=0, F1=1.0, mean reward 0.9524. Oracle also F1=1.0 with privileged access to truth; random/mark-all underperform as adversarial baselines. These figures refer only to *known synthetic development data* and are not a validated blind test.
- Two human-observed CLI demonstrations: older trusted duplicate-invoice prototype TP=1/FP=0/FN=0; clean canonical local episode exact replay, F1=1 and TP=FP=FN=0.

**New PR changes** to dashboard, full transition export and resource profiling are **unverified until the operator reruns pytest and CLI**. Do not carry a parent-branch PASS badge over to untested new commits.

Known limitations: no externally validated financial corpus; restricted currencies/accounting assumptions; some ambiguous/overpayment and cross-currency allocation scenarios not generated; missing full EQT/FAA diagnostics and broad invariance suite; user interface limited to read-only exploration; no standalone trained RL/LLM policy; final hosted GitHub Actions jobs lack runner assignment (issue #29); official judge resource/policy fit still requires manual owner review.

## Reproducibility and safe deployment

- Python >=3.11 for runtime; pinned CPython 3.11 environment for the offline bundle builder.
- Runtime and frontend use only Python standard library; browser assets are included in wheel/sdist as package data.
- The dashboard listens **only** on `127.0.0.1`. It should not be exposed to the public internet or treated as an authentication/security system.
- `verify_integration.py` and `verify_offline_release.py` write sanitized aggregate reports and do not claim official organizer certification.
- Hashes validate delivered bundle file contents, not author identity or full supply-chain provenance.

## Submission sign-off (still open)

The captain/team must agree on repo merge, authorship, choice of license for the team's own code, disclosure of AI assistance and third-party notices, accessibility of the GitHub repository, video recording, slides, Google Drive document and formal contest submission. See `docs/SUBMISSION_CHECKLIST.md`.

This note intentionally does not invent team members, official judge scores, a chosen license, or deployed frontend hosting.
