# LG-026 — Integration gate, CI failure triage, and release handoff

**Date:** 2026-11-21. **Status:** DRAFT / **NOT VERIFIED ON CURRENT HEAD** / **NOT SUBMITTED**. This is a technical verification record, not a license to merge or a competition result.

## Confirmed GitHub Actions observations

Old passing integration run: [PR #25 run 44908652676](https://github.com/Alishka14/genesis-hackathon-2026/actions/runs/44908652676) passed 426/426 tests on CPython 3.11 and 3.12, including the existing Docker and offline bundle checks. **This result only verifies that older commit, not PRs #26–28.**

Since PR #26, GitHub-hosted jobs fail before executing any steps. Investigation used the GitHub Actions API job fields, rather than a guess based on the red CI badge:

| Run | Job label | Runner ID | Steps executed | Conclusion |
| --- | --- | ---: | ---: | --- |
| [44910608524](https://github.com/Alishka14/genesis-hackathon-2026/actions/runs/44910608524) | `ubuntu-latest`, Python 3.11/3.12 | 0 | 0 each | failure |
| [44911516399](https://github.com/Alishka14/genesis-hackathon-2026/actions/runs/44911516399) | `ubuntu-latest`, Python 3.11/3.12 | 0 | 0 each | failure |
| [44911516449](https://github.com/Alishka14/genesis-hackathon-2026/actions/runs/44911516449) | **alternate** `ubuntu-22.04` | 0 | 0 | failure |

All three jobs in the last two runs completed approximately three seconds after starting, with no runner name, test logs, checkout, Python, or Docker steps. The fallback workflow's runner-probe command did not start. **The image-specific hypothesis is weakened. An Actions runner-assignment / account/repository scheduling restriction is plausible, but the exact cause is UNKNOWN.** Do not claim these failures are caused by a Python test.

**Owner action outside code:** open the repository's GitHub **Actions** tab and inspect the run's banner / job failure reason (which is not exposed by this connection). Also check Settings → Actions → General (enabled workflows, policy) and the account/organization's Billing and licensing → Actions usage/budget/payment status. If a GitHub-hosted runner service incident is indicated, review GitHub Status. No billing or permission settings were changed automatically.

## Reproducible offline workaround (Mac/Linux; Python >=3.11)

From a clean clone, use the proposed release-gate branch:

```bash
git fetch origin
git switch agent/integration/lg-026-release-gate
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-role3-test.txt
python scripts/verify_integration.py --mode focused --report integration-focused.json
python scripts/verify_integration.py --mode full --report integration-full.json
```

The gate performs, on a fresh temporary directory:
- a focused or full pytest run;
- mixed 10 train/10 dev companies (8 v1 + 1 v2 clean + 1 v2 fault per split);
- 60 non-oracle action trajectory replays;
- six causal pairs = 12 six-file clean/fault episode variants;
- four baseline-policy comparisons, including deterministic oracle and reconciliation;
- public/private data separation as asserted by the underlying tests;
- **a Git index scan** refusing already-tracked private truth files, provenance, causal labels or `.env` files.

Reports contain only pass/fail status, timings, Python version, counts and aggregate metrics. Synthetic episodes and private truth are generated under a temporary folder and deleted automatically. The tool never claims contest certification. Even `--mode full` marks `docker_isolation_covered=false` and `offline_bundle_covered=false` until the original workflow proves them independently. The local Docker tests can be skipped if Docker Desktop is not running, so a green ordinary pytest run alone cannot prove isolation.

To specifically check the existing Docker runner with a working Docker Engine, run the full suite and inspect the seven original and seven canonical container tests and their skip counts. The existing `role3.yml` job enforces those counts via JUnit XML and is the official integration transport gate.

## Repository hygiene (new preventive fix)

The previous `.gitignore` did not exclude generated `private/truth.json`, `private/provenance.json`, or `private_pair_index.json` from `git add`. This branch ignores those patterns, common local dataset names, and local reports/trajectories. The offline gate checks the **tracked index** and fails if private fixtures are already committed (ignoring filenames alone does not untrack an existing file). Do not use `git add -f` to override protections. A private GitHub repo is not equivalent to secure exposure only to an evaluator.

## Integration and review order

Stack is linear:

1. [PR #20](https://github.com/Alishka14/genesis-hackathon-2026/pull/20): canonical scoring/matcher fixes and independent audit.
2. [PR #23](https://github.com/Alishka14/genesis-hackathon-2026/pull/23): 20 internal financial cases and subprocess cleanup.
3. [PR #24](https://github.com/Alishka14/genesis-hackathon-2026/pull/24): clean hard-negative fixtures and conservative refund validation.
4. [PR #25](https://github.com/Alishka14/genesis-hackathon-2026/pull/25): full six-file v2 split/refund accounting policy and generator (**last fully green CI base**).
5. [PR #26](https://github.com/Alishka14/genesis-hackathon-2026/pull/26): optional mixed 10+10 data, four baselines and false-accusation reporting.
6. [PR #27](https://github.com/Alishka14/genesis-hackathon-2026/pull/27): v2 clean/fault causal counterpart generator and six-pair audit.
7. **PR #28 (this branch):** local integration/release gate, a fixed-runner probe, Git staging leak protection and explicit status report.

All remain separate **draft** PRs. The current integration head has a long change history relative to `main`; do not blindly merge PRs in arbitrary order or mistake a green GitHub mergeability flag for passing the technical gate. **User approval is required before merging, changing repository visibility, inviting reviewers or submitting to GENESIS.**

## Items NOT closed by this PR

- GitHub-hosted runner assignment is still broken; **pytest has NOT run on this final head through CI**.
- Official organizer D01–D20 financial/hidden evaluations and actual RL trained-agent performance are unknown.
- The v2 model lacks fault injections for FX-date and reporting-period; v1 still covers both families and the two original compounds.
- Human review of the v2 financial policy and remittance documentation remains outstanding.
- Contest video, slides, shareable document, judge access, submission confirmation and team AI disclosure must be checked separately before the deadline stated in `docs/SUBMISSION_CHECKLIST.md`.
