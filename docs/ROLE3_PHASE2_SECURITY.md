# Role 3 Phase 2 security and replay

The trusted fixture worker reads private truth and prepares the episode separately from the policy. Its output connects only to the judge. The deadline starts at reset entry. When a public read blocks, the judge terminates the worker and freezes empty findings. If truth was already available, the delegated scorer supplies the corresponding score. If truth was unavailable, the runner reports a timeout with no score. Process creation and cleanup depend on the host operating system and Docker daemon. Cleanup has bounded retries and can report failure to the trusted caller.

The pinned Docker container receives only the copied policy script and JSON messages. The runner uses a read-only root, disabled networking, an unprivileged user, dropped capabilities, CPU and memory limits and no episode, scorer or socket mount. A trusted startup marker distinguishes launcher failure from a policy exiting with the same code. Policy stderr is discarded. The supervisor attempts named-container removal and verifies absence even if client cleanup fails.

Train mode works on generated and supplied files. A trusted terminal diagnostic reports whether the message was written and whether the policy exited during the delivery window. A one-shot submit stays committed when the policy does not read the terminal response. Closed terminal responses expose zero reward and empty info. The Docker tests observe both delivery and the checking policy’s exit code.

Canonical cursors are deterministic and scoped to issuance in the current reset. An old or guessed token cannot authorize access before current issuance. When the same page is legitimately issued again, an identical string has current authority. Exact replay retains literal actions, including JSON null at the budget boundary. Out-of-band faults and timeouts depend on the external clock or supervisor.

| Evidence | Status |
| --- | --- |
| Canonical cursor and replay across processes | VERIFIED_PASS on Windows and Linux |
| Bounded input, malformed messages, crash, blocked reset and deadline handling | VERIFIED_PASS for tested cases |
| Docker filesystem, socket and network restrictions, restricted train and closed delivery | VERIFIED_PASS on GitHub Actions with the pinned image |
| Docker tests on the Windows workstation | NOT_RUN, 13 collected and skipped |
| Organizer host, its kernel and daemon configuration | NOT_RUN |

Run `python -m pytest -q -rs tests/test_isolated_runner.py tests/test_role3_runtime.py tests/test_role3_review.py` on a host with the pinned image. See the [verification report](ROLE3_FINAL_VERIFICATION.md) for exact runs.
