# LG-027 — Offline release and installed-wheel gate

**Date:** 21 November 2026. **Status:** code/tests committed, verification awaiting local CPython 3.11 run. This document is not an organizer certification.

## Context

On macOS with Python 3.14.0 the operator recorded `verify_integration.py --mode full` with `success=true` (all pytest, 20 train/dev episodes, 60 trajectory replays and six paired cases). Subsequently, the focused Docker test command returned **22 passed, 0 failed, 0 skipped** after the Docker Desktop portability correction. Those results are recorded in PR #28 and apply to its local integration branch.

The older complete Docker+offline CI run on PR #25 passed 426/426 on CPython 3.11 and 3.12, **before** LG-024/LG-025/LG-026 additions. Later GitHub-hosted runs failed to allocate any runner (issue #29); they do not provide current-head test results.

This stage evaluates **the installed artifact**, not only the source checkout. The offline package's build command already required Python **3.11**; we preserve that pinned build environment instead of claiming a Python 3.14 build is supported.

## Changes in this PR

- `scripts/prepare_wheelhouse.py`: explicitly networked, one-time download of eight universal wheels with SHA-256 checks from `requirements-build.lock` and `requirements-dev.lock`. Forces the universal Windows-only colorama wheel to be included even when run on macOS.
- `scripts/build_offline_bundle.py`: includes `scripts/` in the final bundle, because recent tests import `scripts.verify_integration`; checks source trees for symlinks, private evaluator data, and environmental secret files before copying anything.
- `scripts/verify_bundle.py`: verifies all listed SHA-256 digests **and the exact bundle file inventory**, rejecting missing/unexpected files, symlinks, path traversal, corrupted or invalid manifests. It does not provide a signed provenance guarantee.
- `scripts/verify_offline_release.py`: offline (no pip index) preparation of clean Python 3.11 build and runtime venvs, build wheel/sdist, manifest verification, runtime installation with hashes, installation of pinned test dependencies, `pip check`, installed-wheel regression tests with **0 skipped**, isolated `ledgergym.role3_demo local`, default 10+10 dataset with 60 trajectory replays. Writes only aggregate sanitized stage metrics, never private answers, in a standalone JSON report.
- `tests/test_offline_release_gate.py`: validation of legitimate vs tampered bundle inventory, unexpected files/symlinks, empty/skipped tests, wrong demo/data metrics, and existing bundle overwrite refusal.

## Commands on macOS

Run from the new branch; Python 3.14 can download wheels but **Python 3.11 must build them**.

```bash
git fetch origin
git switch agent/release/lg-027-offline-package
python3.11 --version
python scripts/prepare_wheelhouse.py "$HOME/ledgergym-wheelhouse-2026"
python3.11 scripts/verify_offline_release.py \
  --wheelhouse "$HOME/ledgergym-wheelhouse-2026" \
  --bundle "$HOME/ledgergym-offline-final-2026" \
  --report "$HOME/ledgergym-offline-report.json"
cat "$HOME/ledgergym-offline-report.json"
```

**Use new directory names** when repeating: wheelhouse preparation and bundle generation refuse to overwrite. `prepare_wheelhouse.py` requires network access and is **not an offline action**; everything under `verify_offline_release.py` is directed to local wheels with `pip --no-index`. This is a package-index restriction, not OS-enforced network isolation. The original Docker runner remains a distinct security mechanism.

The installed test set deliberately focuses on payment scoring and v2 financial controls; it does not replace the original full source pytest + Docker tests. The demo and generated episodes are executed from a temporary working directory outside the Git checkout.

## Expected report contract

```json
{
  "gate": "ledgergym-offline-installed-v1",
  "success": false,
  "contest_certified": false,
  "docker_isolation_covered": false,
  "network_isolation_enforced": false
}
```

The snippet illustrates the initial or failed state, **not an observed result**. A successful run must report `success=true` with every stage `pass`, a verified manifest, installed tests with nonzero count and zero skips, exact replay and 10/10 dataset counts.

Do **not** interpret a green offline report as a full organizer hidden finance pass, proof of runtime network isolation, independent human financial model audit, Docker coverage or permission to merge PRs.

## Release blockers still requiring separate proof

1. Local CPython 3.11 installed-wheel result from this PR and (ideally) a Python 3.12 installed-wheel smoke run.
2. GitHub Actions runner assignment on current head (issue #29).
3. Owner-approved merge of stacked draft PRs, exact checked source commit and tag.
4. Updated README, third-party licenses, human/AI contributions and team approvals.
5. Demo video up to three minutes, presentation, one Google Drive document, verified access, and captain submission before the published deadline.

**No merge, publication, repository access change or contest submission is authorized by this PR.**
