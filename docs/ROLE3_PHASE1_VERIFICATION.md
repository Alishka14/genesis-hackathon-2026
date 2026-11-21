# Role 3 Phase 1 verification

The judge adapter on `agent/environment/lg-role3` exposes generation, environment creation and evaluator-side scoring. It delegates financial generation and matching. File-fed reset keeps supplied IDs, row order, decimal strings and null references. The initial observation has the task, manifest, policy and budget. Every step uses the published result and error shape.

| Contract | Verification |
| --- | --- |
| C01–C06 | Hand-authored files, initial schema, page bounds, repeated pages |
| C07–C15 | Lookup, Decimal calculator, invalid-action costs, terminal submission |
| C16–C17 | Submit at action 100 and truncation after 100 inspections |
| C18 | Deadline at reset entry, blocked file load and policy wait |
| C19 | Train terminal reward, closed zero reward and private evaluator score |
| C20 | Public surface and real Docker tests for isolation, terminal delivery and cleanup |

Malformed findings return null metrics and a trusted return of −1. Role 4 owns known mismatches in the delegated validator and tie-break. The [final verification report](ROLE3_FINAL_VERIFICATION.md) has the verified runtime SHA and results. The [integration report](ROLE3_INTEGRATION_READINESS.md) records what changes when the company generator and offline bundle are added.

The ten review regressions were run against the earlier implementation and failed before the corrections. They cover startup classification, cleanup after a client error, blocked reset, train policy execution, observable terminal delivery, Unicode JSONL and literal null replay. Run them with `python -m pytest -q tests/test_role3_review.py`.
