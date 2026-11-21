# LedgerGym — Independent Reviewer Runbook (LG-040)

**Purpose:** help a second person perform a fresh local run and provide an auditable
report without exposing hidden evaluator truth. These steps are unexecuted on
another machine until a reviewer signs them. Only the already verified source
tree `a2be0a26ac000f311b1934f25bb741ec929e2931` has a recorded full
P0 pass as of 21 November 2026; the LG-040 branch is **NOT_RUN**.

## 1. Preflight and provenance

Clone or checkout the exact review SHA from GitHub. The repository may be
private; obtain read-only access lawfully instead of making it public without
the captain's permission. Use a fresh Python 3.14 venv with pytest for the
P0 aggregator and installed Python 3.11.18 for offline wheel checks.
Docker Desktop or Docker Engine must be running.

```bash
git status --short
git rev-parse HEAD
python --version
python3.11 --version
docker info >/dev/null

IMAGE='python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5'
docker image inspect "$IMAGE" >/dev/null || docker pull "$IMAGE"
```

The exact pinned wheelhouse `ledgergym-wheelhouse-20261121-210839` and
requirements locks must be present locally. Do not claim a network-free build
when installing the wheelhouse required network downloads outside the test.

## 2. New independent financial audit

On a trusted private dataset generated from *new* seed, execute:

```bash
RUN="$HOME/lg040-trusted-$(date +%Y%m%d-%H%M%S)"
python3.11 -m ledgergym.company_dataset "$RUN" --seed 910731 --evaluate --settlement-hard-negatives
python scripts/audit_synthetic_dataset.py "$RUN" \
  --report "$HOME/lg040-independent-audit-$(date +%Y%m%d-%H%M%S).json"
```

The trust-only CLI reads evaluator files for comparison but prints only
aggregate counts, models and issue number. It does not reproduce the source
generator's reconciliation algorithm and recomputes postings/FX/evidence
using Decimal independently. This is a code-path audit, not an accounting
standard certification or a blinded judge episode.

**DO NOT upload `$RUN` or expose `private/truth.json`,
`private/provenance.json` through GitHub/Drive.**

## 3. Adversarial and full API metamorphic checks

```bash
python -m pytest -q -rs \
  tests/test_independent_finance_audit.py \
  tests/test_independent_dataset_cli.py \
  tests/test_financial_env_metamorphic.py \
  tests/test_company_world.py \
  tests/test_company_finance.py \
  tests/test_cab_invariance.py \
  tests/test_company_settlements_v2.py
```

For exact finance scenarios record: alternate cutoff offsets, alternate
foreign code, selected month, seed, expected valid issues, observed TP/FP/FN,
and the first failing stack trace with private IDs redacted.

Never mask a failure by weakening an assertion, rewriting public truth or
altering official `ledgergym/score.py`.

## 4. Full release gate (run from clean checkout)

```bash
REPORT="$HOME/ledgergym-lg040-p0-$(date +%Y%m%d-%H%M%S).json"
BUNDLE="$HOME/ledgergym-lg040-wheel-$(date +%Y%m%d-%H%M%S)"
python scripts/verify_p0_release.py --mode full \
  --wheelhouse "$HOME/ledgergym-wheelhouse-20261121-210839" \
  --bundle "$BUNDLE" --report "$REPORT"
python -m json.tool "$REPORT"
```

Must have `success=true`, all six stages PASS, `docker_isolation_covered=true`
and 22/22 actual Docker tests with 0 skips, installed-wheel stage 10/10
and newly added financial tests passing, clean source SHA in JSON.
A failed stage is a **release blocker**, even if individual tests passed earlier.

The P0 resource observation is a sample, not proof of the official proposed
2 CPU/4 GB/60 s/1 GB limits.

## 5. Check the public handoff artifact

```bash
PUBLIC="$HOME/lg040-public-$(date +%Y%m%d-%H%M%S)"
python scripts/export_submission.py "$RUN" "$PUBLIC"
python scripts/verify_submission_package.py "$PUBLIC"
```

Expected public-only 10+10, 60 trajectories, verified SHA-256 inventory,
no private truth, no new symlinks, no extraneous files. Do not publish
the raw RUN directory. The original Mac verification
`ledgergym-final-public-20261121-233236` passed 125-file / 1,488-transition
checks on the previously tested tree.

## 6. Reviewer handoff checklist

Record exact git SHA, OS, Python/Node/Docker versions, image digest, tool
execution times, new report and bundle paths, result of both independent
audit and original production validators, any discrepancies and their
resolution. Have a person not authoring the code compare at least three
specific invoice/payment/FX/journal examples against source documents.

Status fields remain `contest_certified=false` and
`submission_ready=false` until the captain submits and access is verified.
Do not create new private data exports or modify repository visibility.
