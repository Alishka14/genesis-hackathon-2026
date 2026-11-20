"""Environment component only; financial D01-D20 scenario certification is separate."""
import json

import pytest

import judge_adapter as judge
from ledgergym.flight_recorder import FlightRecorder, verify_replay
from role3_fixture import write_case


@pytest.mark.parametrize("number", range(1, 21), ids=[f"P{n:02d}" for n in range(1, 21)])
def test_paired_transport(tmp_path, number):
    scores = []
    traces = []
    normalized_findings = []
    for side in (0, 1):
        root = tmp_path / str(side)
        rename = side and number >= 6
        reverse = side and (number <= 5 or number >= 11)
        envelope, tables = write_case(root, number, reverse=reverse, rename=rename)
        cfg = {"mode": "closed", "episode_dir": str(root), "team_config": {}}
        recorder = FlightRecorder(judge.make_env())
        initial, info = recorder.reset(28, cfg)
        assert initial["manifest"]["episode_id"] == envelope["episode_id"] and info == {}
        seen = set()
        for table, rows in tables.items():
            cursor = None
            for row in rows:
                obs, reward, t, tr, info = recorder.step(
                    {"name": "list_records", "args": {"table": table, "cursor": cursor, "limit": 1}})
                assert reward == 0 and not t and not tr and info == {}
                assert obs["result"]["records"] == [row]
                cursor = obs["result"]["next_cursor"]
                if "doc_id" in row:
                    doc = row["doc_id"]
                    actual = recorder.step({"name": "get_document", "args": {"doc_id": doc}})[0]
                    assert actual["result"] == row
                    seen.add(doc)
            assert cursor is None
        assert all(set(f["evidence_ids"]) <= seen for f in envelope["findings"])
        canonical = []
        for finding in envelope["findings"]:
            item = dict(finding)
            for key in ("affected_ids", "evidence_ids"):
                item[key] = [x.rsplit("@", 1)[0][::-1] if rename else x.split(" ", 1)[1] for x in item[key]]
            canonical.append(item)
        normalized_findings.append(canonical)
        assert recorder.step({"name": "submit", "args": {"findings": envelope}})[1:4] == (0., True, False)
        steps = len(recorder.rows) - 1
        scores.append(judge.score_episode(root, envelope, steps))
        assert scores[-1]["tp"] == len(envelope["findings"]) and scores[-1]["fp"] == scores[-1]["fn"] == 0
        assert scores[-1]["return"] == pytest.approx(1 - .002 * steps)
        trace = root / "trajectories.jsonl"
        recorder.write(trace)
        rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
        assert rows == recorder.rows
        assert all(set(row) == {"episode_id", "step", "action", "observation", "reward", "terminated", "truncated"}
                   and row["step"] == i and row["episode_id"] == envelope["episode_id"]
                   for i, row in enumerate(rows, 1))
        assert all("hidden-" not in json.dumps(row["observation"]) for row in rows)
        assert verify_replay(judge.make_env(), 28, cfg, initial, rows) == scores[-1]
        traces.append(len(rows))
    assert traces[0] == traces[1] and scores[0] == scores[1]
    assert normalized_findings[0] == normalized_findings[1]


def test_two_file_fed_counterfactuals_with_same_public_ids(tmp_path):
    variants = [write_case(tmp_path / name, 1, duplicate=fault) for name, fault in [("A", False), ("B", True)]]
    assert variants[0][0]["episode_id"] == variants[1][0]["episode_id"]
    findings = variants[1][0]
    doc_id = variants[0][1]["invoices"][1]["doc_id"]
    for ix, name in enumerate(("A", "B")):
        root = tmp_path / name
        cfg = {"mode": "closed", "episode_dir": str(root), "team_config": {}}
        recorder = FlightRecorder(judge.make_env())
        initial, _ = recorder.reset(123, cfg)
        doc = recorder.step({"name": "get_document", "args": {"doc_id": doc_id}})[0]["result"]
        assert doc["line_items"][0]["service_ref"] == ("service B", "service A")[ix]
        assert recorder.step({"name": "submit", "args": {"findings": findings}})[1:] == (0., True, False, {})
        score = judge.score_episode(root, findings, 1)
        assert score["tp"] == ix and score["fp"] == 1-ix
        assert verify_replay(judge.make_env(), 123, cfg, initial, recorder.rows) == score
