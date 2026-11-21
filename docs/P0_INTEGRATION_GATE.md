# P0 integration gate

Review candidate for the financial stack through #16 and the integrated environment branch containing #18. #17 is an independent experimental training branch. The review PR and its Actions checks identify the tested commit. The standalone Role 3 report describes an earlier, smaller tree.

## Reproduce the candidate checks

| Check | Command or CI step | Scope |
| --- | --- | --- |
| Full suite | `python -m pytest -q -rs` | Run with the pinned Docker image present. CI checks that all seven native and seven canonical Docker tests execute. |
| Contract | `python -m ledgergym.role3_mirror` | C01–C20 and twenty transport-only file pairs. C20 requires actual Docker execution. |
| Company | `python docs/verification/role3-company-smoke.py` | Seed 81. Clean 200/20, faulty 400/80, compound 400/80 and maximum 2,000/200 postings/documents. Truth-derived submissions produced 0/4/4/12 TP, zero FP/FN and exact replay. Four inspections per case, zero policy-visible closed rewards and evaluator return 0.992. |
| End-to-end | `python -m ledgergym.role3_demo local --trajectory demo.jsonl` | CI also runs the public walkthrough as an isolated process on an independently authored file episode. Docker tests exercise train and closed. |
| Offline install | Last Python 3.11 CI step | Build from hash-checked wheels, verify the manifest, install in a clean virtual environment with the index disabled, run the installed demo outside the checkout. The build first acquires the locked dependencies. |
| Matcher owner diagnostics | `python docs/verification/p0-matcher-probe.py` | Prints expected and actual results for each example. Diagnostic exit status records execution. Inspect individual PASS/FAIL entries. |

## Release blockers

The published FinTech case and the 20 November check definitions are the acceptance sources. The initial integration candidate had three PASS and six FAIL across nine matcher probes. Historical failures were: repeated affected IDs, repeated evidence IDs, unknown type, lowercase currency, native acceptance of an unaddressable entity reference and M11. The first four return invalid metrics. The native evaluator counts the reference as valid additional evidence, while the canonical adapter rejects it on the same generated files. For M11 the trusted trace observes A→1 and B→0 with TP=2. The specified assignment is A→0 and B→1. Assignment instrumentation is confined to the diagnostic script.

Update on 21 November, evidence/matching follow-up: native and canonical evaluators now share reader-addressable IDs, and maximum matching uses a feasibility-preserving lexicographic tie-break. M11 and native_entity_reference now pass: diagnostics are 5 PASS / 4 FAIL. Duplicate affected/evidence IDs, unknown type and lowercase currency still conflict with the existing strict submission contract. See MATCHER_CONTRACT_DECISIONS.md; their behavior was not silently changed. The older failure description above is retained as historical evidence.

Financial D01–D20 and the full twenty reward checks remain uncertified. Verify all four organizer policies on the same prescribed episode set, independent accounting/provenance and evidence sufficiency for each D case, clean split payments and refunds, currency and timezone boundary variation, and compound causality. The current company reconciliation baseline shares a checker with dataset validation. The payment model's refund and cross-currency allocation limitations are documented in PLAN2_PAYMENT_MATCHING_REPORT.md. The company smoke sends truth-derived findings to exercise transport and score propagation. Official financial/oracle P01–P20 are NOT_RUN pending Role 4 fixes and eligible financial fixtures.

After owner review, land the environment prerequisites (#18 is already in #13) and the financial stack in dependency order #14 → #15 → #16, retaining ancestry when retargeting stacked PRs. Apply this integration candidate once both lines are present. Land owner-reviewed matcher and dataset corrections on the integrated tree, then rerun the full gate before release approval. Confirm offline organizer-host resource limits, the one-command evaluation container, design/submission materials and jury access separately.
