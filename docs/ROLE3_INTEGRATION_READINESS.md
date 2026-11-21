# Role 3 integration readiness

This report compares the Role 3 runtime at `a1cce5e4a22d6b787ae1610cf96147bf6e68c3de` with the following stack. The Role 3 review PR targets #13 so the integrator can review its changes independently.

| Upstream PR | Head tested or inspected | Responsibility |
| --- | --- | --- |
| [#13](https://github.com/Alishka14/genesis-hackathon-2026/pull/13) | `b85f1c1f7e5a8dada21c0c25fe12c706386b7f81` | Shared prototype base |
| [#14](https://github.com/Alishka14/genesis-hackathon-2026/pull/14) | `c2e90e8d8efdbce1a73d18c2606242df7037c49b` | Expanded company generator and provenance |
| [#15](https://github.com/Alishka14/genesis-hackathon-2026/pull/15) | `ce4df7271ae1b2bd265bdd1594386e7a04182801` | Python 3.11 offline bundle |
| [#16](https://github.com/Alishka14/genesis-hackathon-2026/pull/16) | `82719e8fd1731a86fbbd6467db383027d2dd2d0f` | Payment allocation preflight |
| [#17](https://github.com/Alishka14/genesis-hackathon-2026/pull/17) | `4a509f0d26073bc3a534666ebb4d776b135a15d4` | Independent training reference, excluded from the combined tree |

## Reproduced differences

1. **Company provenance.** On the combined source before the temporary compatibility edit, `judge_adapter.generate_episode(81, {"scenario": "company"}, output)` raises `ValueError: matching private company provenance is required`. The two-value dispatcher drops the provenance provided by `company_world.build_company`. The tested worktree fix delegates that scenario to `build_company` and forwards its third return value via `export_episode(..., provenance=provenance)`. This gives the integrator a concrete compatibility patch. An explicit generator API that returns provenance is another way to keep scenario dispatch in Role 2. The company financial logic and scoring formulas were preserved.
2. **Offline packaging.** The current wheel declaration lists only `ledgergym`. The bundle build copies explicit root files and omits `judge_adapter.py`. The temporary solution declares `py-modules = ["judge_adapter"]`, includes the existing `examples` modules for the demo, and adds the adapter to the bundle build's source copy list. The installed test ran outside the source checkout, so it exercised the packaged adapter, reset worker and demo policy.
3. **Documentation merge.** Git reported conflicts in the openings of `README.md` and `docs/INTERFACES.md`. The test worktree retained the upstream company/offline sections and added the canonical judge section. `episode_io.py` merged automatically. It retained physical-line JSONL parsing, company provenance checks and the added nullable fields. The payment allocation preflight uses the existing company path. It does not replace the judge scorer.
4. **Docker test inventory.** PR #15 adds one legacy container test. The Role 3 workflow now requires at least the six original legacy cases, all seven canonical cases, and zero skips in either group. This accommodates the seventh legacy case after integration.

## Combined verification

A separate detached worktree at PR #16 received the Role 3 runtime for verification, with only the compatibility changes above. Neither teammate branch received these changes. The combined pytest run on Windows CPython 3.12.14 returned **292 passed, 0 failed, 14 skipped**. The 14 collected Docker cases were not run in that checkout because the local host lacks the pinned Docker runtime. The standalone Role 3 CI separately exercised its container suite.

The following smoke cases used seed 81. Each went through the canonical generator, export with separated public and private files, file-fed reset, list of records, individual record lookup, document lookup, Decimal calculation, and submit. Closed rewards were zero on every action. Four inspections yielded evaluator return **0.992** in each case. Standalone scoring and literal replay reproduced the terminal result.

| Company | Ledger postings | Documents | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clean | 200 | 20 | 0 | 0 | 0 |
| Faulty, one of each supported type | 400 | 80 | 4 | 0 | 0 |
| Both compound scenarios | 400 | 80 | 4 | 0 | 0 |
| Large, eight single faults and two compounds | 2,000 | 200 | 12 | 0 | 0 |

The expected finding counts were fixed before execution. The submitted oracle findings came from the synthetic trusted truth. This checks integration, evidence addressability and score propagation. Independent financial oracle validation remains an owner task. Re-run the smoke with `python docs/verification/role3-company-smoke.py` in the combined checkout after applying the compatibility changes.

The combined offline bundle built under Windows CPython 3.11.9 using the upstream hash-pinned wheels. Its verifier checked **111 files**. The project wheel installed with `--no-index --require-hashes`. The installed Python 3.11 demo reproduced return **0.994** and exact replay from outside the checkout. The wheel and installed demo also passed on Windows CPython 3.12.14. Production Python dependencies remain empty.

## Integrator handoff

- Reconcile the two documentation openings and approve the provenance handoff with Role 2. Keep the company dataset and legacy evaluator commands when combining the branches.
- Include the judge module and demo policy in the final wheel and staged source. Rebuild and verify the offline artifact on Python 3.11.
- Run the combined tree on the Linux Docker host with the pinned image, then run independent financial/oracle pairs with Roles 2 and 4.
- Keep Role 4's matcher fixes separate from runtime integration. The delegated validator's repeat-ID and semantic mismatch cases are independently reproduced in the Role 3 evidence, and the canonical ambiguity tie-break remains a separate owner issue.
