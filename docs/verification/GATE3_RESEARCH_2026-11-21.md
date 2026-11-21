# LG-030–034: research diagnostics and P0 full trajectory export

Date: 21 Nov 2026. Branch: agent/research/lg-030-034-diagnostics, based on draft PR #32.
Status: CODE COMMITTED / CURRENT-HEAD PYTHON TESTS NOT RUN.

## Implemented code

| Master Plan | Module | Deliverable / limitation |
| --- | --- | --- |
| LG-026/033 | ledgergym/research_robustness.py | Reproducible scorer ID remaps and permutations; bounded deterministic ddmin shrinking. Not a full Hypothesis engine |
| LG-028 | ledgergym/fixture_evaluation.py, ledgergym/replay.py | Full episode/step/action/observation/reward/terminated/truncated records; evaluator-only, open development |
| LG-030 | ledgergym/cab_company_pairs.py, cab_invariance.py | Reversible clean/fault flip for all four v1 families, plus existing six v2 pairs, row shuffle and opaque-ID remapping |
| LG-031 | ledgergym/research_diagnostics.py | EQT sufficient/incomplete/irrelevant/fabricated/undetermined; temporal and contradiction only with verified input annotations |
| LG-032 | ledgergym/research_diagnostics.py | FAA partitions official FP into standard-valid, hard-negative, duplicate and unattributed; clean-case FPR one opportunity per entirely clean company |
| LG-034 | ledgergym/research_report.py | Trusted 10+10, four-policy aggregate diagnostics; scorer consistency, no raw truth exported; dataset index SHA-256 |
| Frontend | ledgergym/dashboard.py, dashboard_static/ | Optional digest-bound /api/research and read-only Evidence & Risk Lab with EQT/FAA aggregate metrics |

These diagnostics do not change canonical judge_adapter, closed agent protocol, official matcher, F1 or reward.

## Full trajectories compatibility

The historical evaluation/trajectories.jsonl is action-only and used by portable replay. To avoid a breaking change, the REQUIRED seven-field event format is now available at:

    evaluation/submission/trajectories.jsonl

Its trace_index.json links records to episode/split/policy, using one-based line offsets.
evaluation/trajectories_full.jsonl keeps trusted split/policy fields. Concrete
executed cursor actions are stable within deterministic development replay;
the action-only file is the portable representation across fresh resets.
Development terminal reward is not suitable for closed-mode agent input.
Before submission, verify the exact organizer file-path expectation.

## Operator's new clean-run commands (Mac)

~~~bash
RUN="$HOME/ledgergym-dev-$(date +%Y%m%d%H%M%S)"
RESEARCH="$HOME/ledgergym-research-$(date +%Y%m%d%H%M%S)"
python3.11 -m ledgergym.company_dataset "$RUN" --evaluate --settlement-hard-negatives
python3.11 -m ledgergym.research_report "$RUN" "$RESEARCH" --trials 8
python3.11 -m ledgergym.cab_company_pairs
python3.11 -m ledgergym.dashboard --dataset "$RUN" \
  --research-report "$RESEARCH/research_summary.json" --port 8765
# Open http://127.0.0.1:8765; stop with Ctrl+C.
~~~

Independent v2 paired benchmark:

~~~bash
PAIRS="$HOME/ledgergym-v2-pairs-$(date +%Y%m%d%H%M%S)"
python3.11 -m ledgergym.v2_pair_dataset "$PAIRS" --evaluate
~~~

## REQUIRED new tests; not yet run on branch HEAD

~~~bash
python -m pytest -q -rs \
  tests/test_research_diagnostics.py \
  tests/test_research_robustness.py \
  tests/test_research_report.py \
  tests/test_cab_company_pairs.py \
  tests/test_cab_invariance.py \
  tests/test_replay.py \
  tests/test_dashboard_and_full_events.py

node --check ledgergym/dashboard_static/app.js

python scripts/verify_p0_release.py --mode focused \
  --report "$HOME/ledgergym-p0-focused-NEW.json"

python scripts/verify_p0_release.py --mode full \
  --wheelhouse "$HOME/ledgergym-wheelhouse-2026" \
  --bundle "$HOME/ledgergym-offline-gate3-NEW" \
  --report "$HOME/ledgergym-p0-full-gate3-NEW.json"
~~~

Use new output directories/report paths per run. Bundle installation verification
now includes research and CAB tests; do not quote the old installed-test count.
On an earlier parent commit the operator observed 22/22 Docker PASS,
60/60 replays and 9/9 offline stages. Those do not validate this branch.

## Remaining human/organizer work

1. Review the ORIGINAL FinTech case PDF; its full content was not accessible
   via the currently available file reader (read empty, materialization 403).
   Monetary tolerance and treatment of unrelated evidence extras are not yet
   certified against the official case.
2. Temporal and contradiction EQT tags still require verified public-policy
   annotations; per-operation validity labels inside faulty episodes absent.
3. The research report is generated from known synthetic data, not an
   independent hidden benchmark. Score invariance tests do not prove a model
   learned causal reasoning.
4. Current HEAD needs source pytest, browser launch, Docker zero-skip and
   fresh offline wheel tests. Hosted runners are blocked (issue #29).
5. Team must choose own-code LICENSE, approve AI/OSS disclosures, merge
   stacked PRs, check judge access, record actual video <=3 minutes and
   submit through the captain. None of those actions is certified complete.

Every report records non-certification explicitly. No secret issue IDs or
private provenance are intentionally exported in research_summary.json.
