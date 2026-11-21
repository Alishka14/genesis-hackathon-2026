# Role 4 independent matcher and reward verification

Base commit `3b25dc0ac298c809d06bcca289bc15c920d9d469`. The acceptance source is the supplied Genesis FinTech case and the 20 November `fintech-checks.txt`, especially the matching normalization, raw limits and lexicographic assignment rules. OpenAI Codex authored the verification. All inputs are synthetic, and the file-based checks use the existing hand-authored `role3_fixture.py` episode.

- The independent oracle enumerates all feasible one-to-one assignments up to five findings and five issues, picking maximum cardinality and then the smallest sorted sequence of (issue ID, finding index) pairs. Three explicit ambiguity cases and 324 seeded configurations cover empty and rectangular graphs, competing assignments, disconnected vertices and Unicode code-point ordering. Tests compare the trusted production assignment itself. The observer is coupled to the scorer's local `paired` variable and restores profiling in a finally block.
- New reward checks exercise 30 versus 31 findings, 10 versus 11 raw evidence entries, boolean and floating amounts, a non-string type, and exact costs at 0, 10, 50 and 100 inspections. The 100-inspection check uses standalone scoring. Episode submit consumes one of the 100 allowed actions.
- The same externally constructed episode and submission produce TP=1, FP=1, FN=0, F1=2/3 and trusted return 47/150 after 10 inspections across the native evaluator, standalone judge adapter, and canonical train and closed runs. The closed policy receives zero reward and empty info. Its observations match the train observations, and the test checks the private fixture ID and scoring fields.
- The tested production matcher agreed with the oracle. A negative control reversed issue ordering in memory and failed all three explicit assignment tests while retaining maximum cardinality. Example reproduction from the first test: two findings each match all four issues. The expected assignment is A→0 and e+U+0301→1. Reversing issue order selected é→1 and 😀→0. Production files were untouched.

## Local commands and results

| Command | Pass | Fail | Skip |
| --- | ---: | ---: | ---: |
| `python -m pytest -q tests/test_score.py tests/test_matcher_p0_regression.py` | 15 | 0 | 0 |
| `python -m pytest -q tests/test_role4_redteam.py` | 15 | 0 | 0 |
| `python -m pytest -q -rs -p no:cacheprovider` | See PR | See PR | See PR |

Local interpreter was Windows CPython 3.12.14 with installed pytest. The review PR records the broader local run and GitHub Actions status. The oracle covers bounded scoring graphs. Official hidden data, complete financial pairs, organizer-host execution and competition scoring are outside this run. The earlier P0 handoff is historical. Its listed normalization, semantic validation, evidence consistency and tie-break defects are addressed on the verified main base. The interface guide still describes pre-fix duplicate handling in its legacy schema section.
