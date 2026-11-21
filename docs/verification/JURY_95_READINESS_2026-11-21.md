# LedgerGym — readiness rubric aiming for 95/100 (21 November 2026)

**Nature of target:** engineering goal and internal forecast, not actual judge result or guaranteed finalist status. The real FinTech evaluation has 20 fixed contract/security checks, 20 hidden finance episodes, 20 reward attacks, 20 paired invariance checks and five engineering items scored 0/1/2. See the six-page official FinTech case, pages 5–6.

## Scorecard: planned tests, not projected earned points

| Criterion | Maximum | Working target | Evidence required |
| --- | ---: | ---: | --- |
| Contract and isolation | 25 | 24 | Strict reset/step, five tools, limits, malformed input, closed-mode Docker (no skipped tests), no leaked truth |
| Data and ground truth | 25 | 24 | 4 fault families, 2 compound, clean controls, causal before/after, money and evidence independently auditable across new seeds |
| Reward and matching | 25 | 24 | Deterministic 1:1 matcher, FP/FN/duplicates, wrong evidence IDs, clean vs faulty, zero/intermediate reward, stable step penalty |
| Reproducibility and generalization | 15 | 14 | Same seed/actions replay and bijective ID/permutation invariance at environment/agent boundary, not just matcher |
| Engineering and explanation | 10 | 9 | One-command run, pinned dependencies, seven-field 60 trajectories, measured failures, honest limits, licensed sources |
| **Total target** | **100** | **95** | **Must be validated, not merely stated** |

## Technical source and gates

The *historical* passing six-stage local P0 was on source commit `c488465a13778a89979bdaeaf2366e6732f9346b`: 22 Docker tests, 101 installed-wheel tests, 162 verified bundle files, 20 synthetic episodes, 60 replays and 6 causal pairs. After merging all 26 pull requests into `main` at `450b1576e9ea543b194f3da725e657b873e3dfbd`, no full P0 on that new SHA was confirmed. LG-039 changes again require a **new** verification.

Run on the checkout (Mac operator; keep repository clean) with the exact pinned Docker image and existing local wheelhouse:

```bash
source .venv/bin/activate
git status --short
git rev-parse HEAD
python -m pytest -q -rs tests/test_export_submission.py tests/test_policy_evidence.py tests/test_faa_operation_cases.py
REPORT="$HOME/ledgergym-95-gate-$(date +%Y%m%d-%H%M%S).json"
BUNDLE="$HOME/ledgergym-95-bundle-$(date +%Y%m%d-%H%M%S)"
python scripts/verify_p0_release.py --mode full --wheelhouse "$HOME/ledgergym-wheelhouse-20261121-210839" --bundle "$BUNDLE" --report "$REPORT"
python -m json.tool "$REPORT"
```

**PASS requirements:** `success=true` and 6/6 named stages passing, 0 Docker skips, source SHA recorded and clean, correct 10-stage no-index installed wheel. Neither `contest_certified` nor `submission_ready` is set by this command.

## Verified public artifact before external sharing

```bash
RUN="$HOME/ledgergym-development-$(date +%Y%m%d-%H%M%S)"
PUBLIC="$HOME/ledgergym-jury-public-$(date +%Y%m%d-%H%M%S)"
python3.11 -m ledgergym.company_dataset "$RUN" --seed 2026 --settlement-hard-negatives --evaluate
python scripts/export_submission.py "$RUN" "$PUBLIC"
python scripts/verify_submission_package.py "$PUBLIC"
```

An independently executed verifier checks exact 10+10 public episode inventory, 60 non-oracle baseline traces, seven fields/transition, SHA-256 for every file, correct line mapping, and absence of extra private files and malformed evidence fields. The exporter invokes the same verifier before its atomic final rename. Source `RUN` includes evaluator-private `truth.json` and `provenance.json`: **never zip or publish the source dataset**. A verified public artifact remains an *open synthetic development* set, not a blinded independent test.

## Highest-priority adversarial questions for humans

1. **Validator independence.** Synthetic financial invariants and reference reconciliation share modeling assumptions. Arrange at least one separate human-finance check of invoices, allocations, FX cutoff, reports and each truth evidence set.
2. **Amount tolerance.** The official case requires an explicitly stated tolerance but gives no numerical value. Current matcher requires exact integer minor-unit amount equality. Keep this public and obtain organizer clarification; do not infer or silently change monetary tolerances.
3. **Unseen parameter combinations.** Include cross-seed cases, timezone offsets, currency settings, permutations and renaming to probe for shortcut leaks; distinguish scorer-only invariance from full environment equivalence.
4. **Resource limits.** The 2 CPU / 4 GiB / 60-sec per episode / 1 GiB package line is *proposed* in the case. A single local RSS observation is not a hard-enforced limit.
5. **CI after merge.** GitHub-hosted jobs may fail to be scheduled. Capture explicit results from actual Mac Docker + Python 3.11 verification, not a green PR or an unassigned workflow.

## LG-039 isolated verifier evidence (21 November)

A local Python 3.13 test harness checked **byte-identical** GitHub blobs `scripts/export_submission.py` (Git blob `d6138999a9cb3664c32d8b546f67b6b814f6ba39`) and `scripts/verify_submission_package.py` (Git blob `d274d8bc33715d97bbcfa4401b948d671b6373ea`). The original isolated export fixtures also passed **5/5**. An additional five direct checks passed: a valid synthetic 10 train + 10 dev export with 60 traces and 125 files; altered payments file SHA failure; extra private truth file rejection; private `seed` injection with recomputed checksum rejection; symlink rejection. These checks do **not** run the actual 10+10 LedgerGym company generator, new 50+ parameter adversarial matrix, the full P0 gate or the installed wheel.

GitHub Actions for this PR returned **failure without any execution steps** in all jobs (Python 3.11, 3.12, alternate Ubuntu 22.04). This is a runner/scheduling blocker, not evidence of a failing pytest assertion. The Mac release owner must run the tests and full P0; status remains **NOT_VERIFIED** for final integrated code.

## Human-owned submission items — not completed by code merge

- [ ] Confirm 2–4 official team members, captain and human author/contribution mapping.
- [ ] Approve **the project's own LICENSE**, retain `THIRD_PARTY_NOTICES.md`, and disclose AI/Codex.
- [ ] Record a real demo **≤3 minutes**, show actual CLI/environment findings and restrictions; no simulated judge scores.
- [ ] Upload finished deck and full public dataset bundle; verify external read-only access to each link and repository.
- [ ] Put links into a Google Drive document and check the current submission form in Genesis account.
- [ ] Captain submits **by 22 November 2026 23:59 Astana** and retains an acknowledgment.

**Stop condition:** If new full P0 fails, if hidden truth is exposed, if team authorization/licensing is missing, or if the package is inaccessible to judges, do not call the submission contest-ready or claim 95 points.

**AI/source disclosure:** This LG-039 quality-gate improvement was authored with ChatGPT/GPT-6 and the connected GitHub tool. No third-party project sources were copied into this change; standard-library-only jury package verifier. Independent test results and captain sign-off are still required.
