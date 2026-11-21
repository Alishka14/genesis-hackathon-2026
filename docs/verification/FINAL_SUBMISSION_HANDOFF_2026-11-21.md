# LedgerGym / GENESIS FinTech — submission handoff (draft)

Date: 21 Nov 2026. Source of deadline and delivery requirements: `docs/SUBMISSION_CHECKLIST.md` citing the uploaded 2026 competition regulation. **Deadline stated there: 22 Nov 2026, 23:59 Astana time.** This checklist is a handoff only. It neither submits any material nor asserts that the captain has approved a release.

## Proven engineering evidence

| Evidence | Observed result | Limits |
| --- | --- | --- |
| Full local integration on macOS, Python 3.14.0 | `success=true`; pytest, mixed generator, causal pairs and tracked-private-files stages PASS | Not GitHub-hosted CI or organizer-certified |
| Dataset evaluation | 20 train/dev episodes; 8 v1 + 2 v2 per split; 60 replayed trajectories | Development fixture, not blind/hidden benchmark |
| Causal counterpairs | Six pairs, 12 variants, eight audited fault issues, 0 clean false accusations | Synthetic paired controls only |
| Real Docker container tests | 22 passed; zero failed/skipped | Local Docker Desktop; separate from integration JSON |
| Offline installed-wheel gate, CPython 3.11.18 | 9 stages PASS; 45 tests passed without skips; exact demo replay; 145 SHA256-file checks | `pip --no-index` prevents use of PyPI in package installs, does not force kernel network isolation |
| Canonical demonstration | `VERIFIED_PASS`, four actions, `replay=exact`, F1=1, return=.994, TP=FP=FN=0 | **Clean episode**; does not demonstrate detecting a fault |
| Git/source provenance | Operator: source tree diff to PR #30 empty; clean `agent/release/lg-027-offline-package` at `b19b889` | New draft submission branch must be reviewed separately |
| GitHub Actions on later branches | Runner scheduling failures before steps | Issue #29; CI on final head not verified |

**Never represent `contest_certified=false` as competition acceptance.** Synthetic `private/truth.json` files are permitted inside generated local development episodes; keep them out of the Git repository and the video.

## Required captain/owner decisions

- [ ] Confirm team membership, captain and individual contributions by filenames/modules. Do not invent authorship; verify `docs/SCOPE.md`.
- [ ] Review and explicitly approve merging stacked PRs **#20, #23, #24, #25, #26, #27, #28, #30** plus this new documentation PR; check the exact integrated main commit and rerun at least the integration gate.
- [ ] Verify the licensing of original team-authored code and `THIRD_PARTY_NOTICES.md`; include permitted licenses and the source/usage of any outside code or libraries.
- [ ] Record how AI was used in planning, code generation, testing, review and documentation, and which output the team checked or modified. Do not claim development was completely unaided.
- [ ] Check public/read-only access to GitHub: repository is currently **private**. Adding a URL alone does not give judges access. Choose visibility or explicit judge invitations in line with team approval.
- [ ] Record the demo video in `docs/verification/DEMO_RECORDING_2026-11-21.md`; keep it at or below 3:00.
- [ ] Assemble presentation (recommended <=14 slides): problem, finance evidence, LedgerGym solution, public/private boundaries, architecture, demo, 4 baseline policies, clean/hard-negative examples, causal pairs, observed results, security/offline reproducibility, limitations, responsible AI/OSS disclosures, next steps.
- [ ] Prepare one Google Drive document with checked links to repo, video, presentation and needed artifacts; test every link in an account with the same permissions as a judge.
- [ ] Captain submits the Google Drive document URL on `genesis-exe.com` **before 22 Nov 23:59 Astana** and saves the timestamp/confirmation.

## Copyable submission document template

```text
GENESIS Hackathon 2026 — FinTech
Project: LedgerGym
Team: [verified team name]
Captain: [verified captain name]

Repository: [verified URL, with actual judge access]
Demo (duration <=3 min): [published video link]
Presentation: [published slides link]
Offline technical release: [optional link; tested artifact]
Documentation and AI/open-source disclosure: [link to README/approved disclosure]
Verified source commit: [final approved SHA]

Project summary:
LedgerGym is a synthetic financial-audit environment. It exposes
bounded tools for inspecting invoices, payments, ledger entries and
evidence, while keeping evaluator truth outside the untrusted policy.
It provides repeatable synthetic scenarios, scoring and baseline tests.

Current observed test evidence:
- Local integration gate: PASS.
- Local Docker isolation: 22/22 PASS.
- Offline installed-wheel gate, CPython 3.11.18: 9/9 stages,
  45/45 installed tests PASS, 145 bundle files hash-checked.
- Local canonical demo: exact replay, clean episode.
These do not claim external benchmark or official certification.

Last access check (Astana time): [date/time]
Submitter and confirmation: [captain fills after submitting]
```

## Open technical risks

1. GitHub Actions cannot schedule runners on recent commits; restore and run CI if possible, but do not misrepresent the cause or conflate it with a test assertion failure.
2. Full installed-wheel tests cover a focused 45-test subset; the separate source suite and real Docker run cover more cases.
3. Evaluation uses synthetic scenarios and internal public checks; external real-world accuracy and security are not established.
4. Private truth must never be mounted into an agent container, uploaded in the public demo or committed with source.
5. New documentation and any subsequent merges move the commit SHA. Track the exact final checked commit.

This is a draft handoff intended for human review. No external action has been taken by the documentation process.
