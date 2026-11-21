# Role 3 final verification

Role 3 review branch `agent/environment/lg-role3` targets `agent/environment/lg-013` ([PR #13](https://github.com/Alishka14/genesis-hackathon-2026/pull/13)). Runtime hardening was verified at `a1cce5e4a22d6b787ae1610cf96147bf6e68c3de`. The [integration report](ROLE3_INTEGRATION_READINESS.md) records the separate test against PRs #14–16 and the remaining owner decisions.

| Run | Pass | Fail | Skip | Not run |
| --- | ---: | ---: | ---: | ---: |
| Windows CPython 3.11.9, pytest 8.4.2 | 197 | 0 | 13 | 13 Docker cases |
| Windows CPython 3.12.14, pytest 8.4.2 | 197 | 0 | 13 | 13 Docker cases |
| Ubuntu CPython 3.11.18 with pinned Docker | 210 | 0 | 0 | 0 collected tests |
| Ubuntu CPython 3.12.16 with pinned Docker | 210 | 0 | 0 | 0 collected tests |

The skip and not-run columns describe the same 13 local Docker tests. The [runtime CI run](https://github.com/Alishka14/genesis-hackathon-2026/actions/runs/44881315145) ran all seven canonical and six legacy Docker cases on each Python version. The previous 197-test CI run applies to `4752460` before the review corrections. GitHub reports the exact head checks on the review PR.

From the repository root:

```sh
python -m pip install -r requirements-role3-test.txt
python -m pytest -q -rs -p no:cacheprovider
python -m ledgergym.role3_mirror --output role3-mirror.json
python -m ledgergym.role3_demo local --trajectory trajectories.jsonl
python -m ledgergym.role3_demo restricted --episode PATH --trajectory restricted-trajectories.jsonl
```

The 20 canonical C checks were exercised. C20 includes real container evidence from CI, with the local result recorded separately. The 20 paired tests verify the environment portions of P01–P20 using hand-authored files and expected answers. Full official financial and oracle paired compliance remains outside these results. The native regressions also run. Both CI jobs executed the restricted demo on a hand-authored file episode. The policy listed records, retrieved a document, calculated, and submitted. Its visible rewards were zero and the evaluator return was 0.994, with exact replay.

The existing Flight Recorder and exact replay satisfy the trajectory requirement. Optional investigation analytics were deferred to keep the release focused. Role 4 owns duplicate ID normalization, semantic mismatch handling and canonical tie-break. The first two behaviors are reproduced in [owner-blocker evidence](verification/role3-owner-blockers.json). The Role 2 and integrator dependencies are recorded in the integration report.

Sources were the supplied Genesis FinTech case, `fintech-checks.txt`, the Role 3 brief, actual project code and tests, and the earlier 111-row independent audit. The checks operate on synthetic data.

Demo explanation, approximately 35 seconds:

> LedgerGym now accepts the judge’s standard actions and can load an external company without changing its identifiers or record order. A policy can inspect records and documents, calculate with decimal arithmetic, and submit within 100 actions. In closed mode, the policy sees zero reward while the evaluator keeps the actual score. We capture each transition and replay the same actions exactly. The Docker runner separates the policy from the evaluator. CI exercised private-file and socket access, network restrictions, timeouts, and reward delivery in both closed and train modes.
