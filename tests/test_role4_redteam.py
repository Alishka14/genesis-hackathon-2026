"""Independent matcher and reward checks on bounded synthetic fixtures."""

from itertools import product
import json
import random
import sys

import pytest

import judge_adapter
from ledgergym import runtime
from ledgergym.episode_io import load_public_episode
from ledgergym.score import evaluate
from role3_fixture import write_case


def exhaustive_assignment(issue_ids, neighborhoods):
    """Enumerate assignments, including unmatched issues, for at most 5x5."""
    assert len(issue_ids) <= 5 and len(neighborhoods) <= 5
    choices = [
        [None, *(i for i, neighbors in enumerate(neighborhoods) if issue in neighbors)]
        for issue in issue_ids
    ]
    best = ()
    for selected in product(*choices):
        used = [i for i in selected if i is not None]
        if len(set(used)) != len(used):
            continue
        candidate = tuple(sorted((issue, i) for issue, i in zip(issue_ids, selected) if i is not None))
        if (-len(candidate), candidate) < (-len(best), best):
            best = candidate
    return best


def assert_graph(issue_ids, neighborhoods):
    # One evidence token per finding encodes the arbitrary graph without using
    # the scorer's edge rules to derive the reference assignments.
    tokens = [f"D{i}" for i in range(len(neighborhoods))]
    common = {"type": "duplicate_invoice", "affected_ids": ["R"], "currency": "KZT"}
    issues = [
        dict(common, issue_id=issue, expected_amount_minor=100,
             allowed_evidence_sets=[[token] for token, neighbors in zip(tokens, neighborhoods) if issue in neighbors])
        for issue in issue_ids
    ]
    findings = [
        dict(common, claimed_amount_minor=100, evidence_ids=[token], explanation="")
        for token in tokens
    ]
    observed = []

    def record_assignment(frame, event, _result):
        if event == "return" and frame.f_code is evaluate.__code__:
            observed.append(tuple(sorted((issue_ids[j], i) for j, i in frame.f_locals["paired"].items())))

    # Read the trusted assignment without changing the production API or output.
    previous = sys.getprofile()
    try:
        sys.setprofile(record_assignment)
        result = evaluate(issues, findings, {"R", *tokens}, 0)
    finally:
        sys.setprofile(previous)

    expected = exhaustive_assignment(issue_ids, neighborhoods)
    assert observed == [expected], (issue_ids, neighborhoods)
    assert (result["tp"], result["fp"], result["fn"]) == (
        len(expected), len(findings) - len(expected), len(issues) - len(expected)
    )


@pytest.mark.parametrize("issue_ids,neighborhoods", [
    (("😀", "é", "e\u0301", "A"), ({"😀", "é", "e\u0301", "A"},) * 2),
    (("D", "C", "B", "A"), ({"A", "B"}, {"A"}, {"B", "C", "D"}, {"C", "D"})),
    (("C", "B", "A"), ({"A", "C"}, {"A", "B"}, set())),
])
def test_explicit_ambiguous_graphs(issue_ids, neighborhoods):
    assert_graph(issue_ids, neighborhoods)


@pytest.mark.parametrize("seed", [7, 2026, 91073])
def test_seeded_small_graphs(seed):
    rng = random.Random(seed)
    alphabet = ("😀", "é", "e\u0301", "β", "Z")
    for issue_count, finding_count in product(range(6), repeat=2):
        issue_ids = rng.sample(alphabet, issue_count)
        for density in (0.2, 0.5, 0.8):
            neighborhoods = [
                {issue for issue in issue_ids if rng.random() < density}
                for _ in range(finding_count)
            ]
            assert_graph(issue_ids, neighborhoods)


def assert_metrics(score, counts, reward, *, reward_key="return"):
    assert tuple(score[key] for key in ("tp", "fp", "fn")) == counts
    assert score[reward_key] == pytest.approx(reward, abs=1e-9, rel=0)


@pytest.mark.parametrize("steps,reward", [(0, 1), (10, .98), (50, .90), (100, .80)])
def test_exact_inspection_cost(tmp_path, steps, reward):
    answer, _ = write_case(tmp_path, number=6)
    assert_metrics(judge_adapter.score_episode(tmp_path, answer, steps), (1, 0, 0), reward)


@pytest.mark.parametrize("field,bad", [
    ("claimed_amount_minor", True),
    ("claimed_amount_minor", 15706.0),
    ("type", 1),
])
def test_malformed_finding_invalidates_valid_sibling(tmp_path, field, bad):
    answer, _ = write_case(tmp_path, number=6)
    finding = answer["findings"][0]
    answer["findings"].append(dict(finding, **{field: bad}))
    assert_metrics(judge_adapter.score_episode(tmp_path, answer, 10), (None, None, None), -1)


def test_submission_and_raw_evidence_boundaries(tmp_path):
    answer, _ = write_case(tmp_path, number=6)
    finding = answer["findings"][0]
    # Ten raw IDs normalize to the two complete evidence IDs. Thirty identical
    # findings score one TP and 29 FP (F1 = 2/31).
    ten = finding["evidence_ids"] * 5
    findings = [dict(finding, evidence_ids=ten)] * 30
    at_limit = dict(answer, findings=findings)
    assert_metrics(judge_adapter.score_episode(tmp_path, at_limit, 10), (1, 29, 0), 4 / 31 - 1.02)
    for invalid in (
        findings + findings[:1],
        findings[:-1] + [dict(finding, evidence_ids=ten + ten[:1])],
    ):
        assert_metrics(judge_adapter.score_episode(tmp_path, dict(answer, findings=invalid), 10),
                       (None, None, None), -1)


def test_file_fixture_score_agrees_across_interfaces(tmp_path, monkeypatch):
    answer, _ = write_case(tmp_path, number=6)
    public = load_public_episode(tmp_path / "public")
    truth = json.loads((tmp_path / "private/truth.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(runtime, "generate_episode", lambda seed, config: (public, truth))
    _, native_score = runtime.create_episode(6)

    # One correct finding and one structurally valid accusation in USD.
    finding = answer["findings"][0]
    answer["findings"].append(dict(finding, currency="USD"))
    expected = {"tp": 1, "fp": 1, "fn": 0, "precision": .5, "recall": 1,
                "f1": 2 / 3, "return": 47 / 150}
    file_score = judge_adapter.score_episode(tmp_path, answer, 10)
    assert file_score == pytest.approx(expected, abs=1e-9, rel=0)
    native = native_score(answer["findings"], 10)
    native["return"] = native.pop("reward")
    assert native == pytest.approx(expected, abs=1e-9, rel=0)

    public_transcripts = {}
    for mode in ("train", "closed"):
        env = judge_adapter.make_env()
        initial, info = env.reset(6, {"mode": mode, "episode_dir": str(tmp_path)})
        assert info == {} and env.final_score is None
        steps = [env.step({"name": "calculator", "args": {"expression": "1+1"}}) for _ in range(10)]
        steps.append(env.step({"name": "submit", "args": {"findings": answer}}))
        assert all(step[1:] == (0, False, False, {}) for step in steps[:-1])
        _, reward, terminated, truncated, info = steps[-1]
        assert (terminated, truncated, info) == (True, False, {})
        assert reward == pytest.approx(0 if mode == "closed" else expected["return"], abs=1e-9, rel=0)
        assert env.final_score == file_score
        public_transcripts[mode] = [initial, *(step[0] for step in steps)]
        if mode == "closed":
            assert "hidden-dupe" not in json.dumps(public_transcripts[mode])
            for public_obs in public_transcripts[mode]:
                assert set(expected).isdisjoint(public_obs)
                assert set(expected).isdisjoint(public_obs.get("result") or {})
    assert public_transcripts["train"] == public_transcripts["closed"]
