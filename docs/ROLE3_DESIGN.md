# Role 3 runtime design

Authorized scope: all three Role 3 phases and a reviewable PR, without merging. Base: `b85f1c1f7e5a8dada21c0c25fe12c706386b7f81`, branch `agent/environment/lg-role3`.

The existing package remains the implementation. The root judge adapter translates the published transport and delegates generation/export and scoring to their existing owners. The canonical environment adapts the native sandbox's reads and Decimal calculator and runs in the trusted judge process. The restricted runner delivers only JSON observations/actions to a policy container; neither the episode directory nor the scorer package is mounted into it.

Alternatives considered: rewriting the environment would duplicate the native behavior and expand review risk; making the legacy protocol canonical in place would break existing callers and cursor tests. A thin canonical wrapper with explicit deterministic pagination preserves the existing consumers while supplying the organizer protocol. This implementation choice follows the user's request to preserve the prototype.

Canonical input is `{name,args}`. Reset supplies `task`, `manifest`, `policy`, `remaining_steps`; steps supply `result`, `error`, `remaining_steps`. A submitted findings object contains `episode_id` and its findings list. Closed rewards are always zero, with empty public info. Private scoring remains judge-side. External loading preserves supplied values, order and identifiers, and never falls back to generation on load error.

The action budget is 100 including submit; inspection cost excludes submit. An invalid action consumes a step. Submit at action 100 is valid; the 100th inspection truncates with empty findings. The supervisor deadline starts at reset entry and includes policy execution. Completion freezes results until reset. Public failures have bounded fixed codes/messages.

Deterministic cursor authority is an issuance registry scoped to the current reset. Cursor contents depend on public episode content and page identity, not hidden seed or truth. Reset removes authority; old or guessed strings fail before this reset has issued the corresponding page. Identical public episodes necessarily issue identical strings after the same actions. Once the current reset legitimately reissues an identical token, its origin as a previously observed string cannot be distinguished. Requiring both exact replay and rejection even after reissuance is incompatible; the contract resolution is current issuance, not historical string freshness. Native legacy behavior stays available for compatibility.

The adapter and recorder are trusted components, not Python-object security boundaries. Real hostile policies must use the restricted runner. Hostile-container tests may be reported VERIFIED_PASS only when the actual pinned Docker runtime is exercised. A missing Docker runtime is NOT_RUN, never simulated proof of isolation. Optional analytics are deferred while that critical verification gate is open.

Independent hand-authored fixtures, literal numeric expectations, exact raw replay and bounded state sequences verify the environment. Financial mutations and matching methodology remain Role 2/4 responsibilities. Known upstream normalization, provenance and data-diversity limitations must remain visible in the handoff and PR.
