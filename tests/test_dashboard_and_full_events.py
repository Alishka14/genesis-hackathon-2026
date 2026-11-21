"""P0: full development events and local dashboard public-only boundary."""
import json
from pathlib import Path
import threading

import pytest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ledgergym.company_dataset import create_company_dataset
from ledgergym.dashboard import dashboard_server
from ledgergym.fixture_evaluation import evaluate_fixture_dataset


def _dataset(tmp_path):
    root = tmp_path / "synthetic"
    create_company_dataset(root, seed=2026, include_settlement_hard_negatives=True)
    summary = evaluate_fixture_dataset(root, root / "evaluation")
    return root, summary


def test_full_events_have_public_observations_rewards_and_exact_stable_order(tmp_path):
    root, summary = _dataset(tmp_path)
    path = root / "evaluation" / "trajectories_full.jsonl"
    assert path.is_file()
    first = path.read_bytes()
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(events) > 60
    assert sum(bool(row["terminated"]) for row in events) == 60
    assert not any(row["truncated"] for row in events)
    assert all(set(row) == {
        "episode_id", "split", "policy", "step", "action",
        "observation", "reward", "terminated", "truncated",
    } for row in events)
    assert all(row["policy"] != "oracle" for row in events)
    assert all(isinstance(row["reward"], (float, int))
               and isinstance(row["observation"], dict) for row in events)
    # These answers and evaluator-only fields must never enter a trajectory.
    for forbidden in (
        '"issue_id"', '"allowed_evidence_sets"', '"expected_amount_minor"',
        '"provenance"', '"private_pair_index"', '"interventions"', '"seed"',
    ):
        assert forbidden not in first.decode("utf-8")
    submission = root / "evaluation" / "submission"
    public_lines = [
        json.loads(line)
        for line in (submission / "trajectories.jsonl").read_text().splitlines()
    ]
    public_fields = {
        "episode_id", "step", "action", "observation", "reward",
        "terminated", "truncated",
    }
    assert len(public_lines) == len(events)
    assert all(set(row) == public_fields for row in public_lines)
    assert public_lines == [
        {key: value for key, value in event.items() if key in public_fields}
        for event in events
    ]
    index = json.loads((submission / "trace_index.json").read_text())
    assert index["closed_mode"] is False
    assert index["private_truth_exported"] is False
    assert len(index["trajectories"]) == 60
    assert sum(row["steps"] for row in index["trajectories"]) == len(public_lines)
    assert index["trajectories"][0]["first_line"] == 1
    assert all(forbidden not in (submission / "trajectories.jsonl").read_text()
               for forbidden in (
                   '"issue_id"', '"allowed_evidence_sets"',
                   '"expected_amount_minor"', '"provenance"',
               ))
    assert summary["replay"] == {"trajectories": 60, "score_matches": 60}
    # Evaluating a second time must be byte-stable despite pagination cursors.
    output = tmp_path / "again"
    evaluate_fixture_dataset(root, output)
    assert first == (output / "trajectories_full.jsonl").read_bytes()


def test_local_dashboard_serves_only_whitelisted_public_resources(tmp_path):
    root, summary = _dataset(tmp_path)
    with dashboard_server(root, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = "http://127.0.0.1:" + str(server.server_address[1])

        def get(path):
            with urlopen(address + path, timeout=10) as response:
                return response.status, response.read(), response.headers

        try:
            code, html, headers = get("/")
            assert code == 200 and b"LEDGERGYM" in html
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
            for path in ("/app.css", "/app.js"):
                assert get(path)[0] == 200
            # A malicious website must not access a loopback-only local
            # dashboard using DNS rebinding or a foreign Origin.
            for malicious_headers in (
                {"Host": "attacker.example"},
                {"Origin": "https://attacker.example"},
            ):
                request = Request(address + "/api/summary",
                                  headers=malicious_headers)
                try:
                    urlopen(request, timeout=10)
                except HTTPError as exc:
                    assert exc.code == 403
                    assert b'"local_origin_required"' in exc.read()
                else:
                    raise AssertionError("foreign origin reached local API")
            assert json.loads(get("/api/research")[1]) == {"status": "not_run"}
            health = json.loads(get("/api/health")[1])
            assert health == {"status": "ok", "mode": "local_read_only",
                              "dataset": "synthetic_development"}
            exposed = json.loads(get("/api/summary")[1])
            assert exposed["policies"]["reconciliation"] == summary["policies"]["reconciliation"]
            assert "private" not in exposed
            index = json.loads(get("/api/episodes")[1])
            assert len(index["train"]) == len(index["dev"]) == 10
            entry = index["train"][0]["name"]
            endpoint = ("/api/records?split=train&episode=" + entry
                        + "&table=invoices&page=0")
            code, body, _ = get(endpoint)
            assert code == 200
            data = json.loads(body)
            assert data["table"] == "invoices"
            assert 0 < len(data["records"]) <= 50
            assert data["total"] >= len(data["records"])
            for secret in (b'"truth"', b'"issues"', b'"provenance"', b'"private_pair_index"'):
                assert secret not in body
            findings_url = "/api/findings?split=train&episode=" + entry
            _, findings_body, _ = get(findings_url)
            findings = json.loads(findings_body)
            assert findings["engine"] == "deterministic_public_reconciliation"
            assert findings["independent_validation"] is False
            assert findings["private_truth_used"] is False
            assert findings["count"] == len(findings["findings"])
            assert all(set(item) <= {
                "type", "affected_ids", "claimed_amount_minor",
                "currency", "evidence_ids", "explanation"
            } for item in findings["findings"])
            assert all(secret not in findings_body for secret in (
                b'"truth"', b'"provenance"', b'"allowed_evidence_sets"',
                b'"issue_id"', b'"expected_amount_minor"'))
            replay_url = ("/api/replay?split=train&episode=" + entry
                          + "&policy=reconciliation")
            _, replay_body, _ = get(replay_url)
            replay = json.loads(replay_body)
            assert replay["format"] == "full_transitions"
            assert len(replay["steps"]) > 1
            assert replay["steps"][0]["step"] == 1
            assert replay["steps"][-1]["terminated"] is True
            assert replay["steps"][-1]["action"] == "submit"
            assert replay["steps"][-1]["reward"] is not None
            assert all(secret not in replay_body for secret in (
                b'"truth"', b'"provenance"', b'"private_pair_index"',
                b'"allowed_evidence_sets"', b'"issue_id"'))
            for bad_url, expected in (
                ("/private/truth.json", 404),
                ("/api/records?split=train&episode=../../private&table=ledger&page=0", 400),
                ("/api/records?split=train&episode=" + entry
                 + "&table=private&page=0", 400),
                ("/api/records?split=train&episode=" + entry
                 + "&table=ledger&page=0&extra=1", 400),
                ("/api/records?split=train&episode=" + entry
                 + "&table=ledger&page=1001", 400),
                ("/api/replay?split=train&episode=" + entry
                 + "&policy=oracle", 400),
                ("/api/findings?split=train&episode=../../private", 400),
                ("/api/findings?split=train&episode=" + entry
                 + "&source=truth", 400),
                ("/api/replay?split=train&episode=../../private"
                 + "&policy=reconciliation", 400),
                ("/api/replay?split=train&episode=" + entry
                 + "&policy=reconciliation&secret=1", 400),
            ):
                try:
                    get(bad_url)
                except HTTPError as exc:
                    assert exc.code == expected
                else:
                    raise AssertionError("unsafe URL was accepted: " + bad_url)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def test_replay_falls_back_to_legacy_action_only_dataset(tmp_path):
    root, _ = _dataset(tmp_path)
    (root / "evaluation" / "trajectories_full.jsonl").unlink()
    with dashboard_server(root, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = "http://127.0.0.1:" + str(server.server_address[1])
            with urlopen(address + "/api/episodes", timeout=10) as response:
                episode = json.load(response)["train"][0]["name"]
            url = (address + "/api/replay?split=train&episode=" + episode
                   + "&policy=reconciliation")
            with urlopen(url, timeout=10) as response:
                replay = json.load(response)
            assert replay["format"] == "actions_only"
            assert len(replay["steps"]) > 1
            assert replay["steps"][-1]["action"] == "submit"
            assert all(step["reward"] is None for step in replay["steps"])
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_dashboard_rejects_symlink_public_file(tmp_path):
    root, _ = _dataset(tmp_path)
    invoice = root / "train" / "episode-00" / "public" / "ledger.csv"
    invoice.unlink()
    invoice.symlink_to(root / "train" / "episode-00" / "private" / "truth.json")
    with dashboard_server(root, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = "http://127.0.0.1:" + str(server.server_address[1])
            url = address + "/api/records?split=train&episode=episode-00&table=ledger&page=0"
            try:
                urlopen(url, timeout=10)
            except HTTPError as exc:
                assert exc.code == 500
                assert b'"local_dataset_unavailable"' in exc.read()
            else:
                raise AssertionError("symlinked dataset unexpectedly served")
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_public_findings_match_known_synthetic_training_cases_without_truth_api(tmp_path):
    root, _ = _dataset(tmp_path)
    with dashboard_server(root, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = "http://127.0.0.1:" + str(server.server_address[1])
        try:
            with urlopen(address + "/api/episodes", timeout=10) as response:
                index = json.load(response)
            faulty = clean = 0
            for split in ("train", "dev"):
                for episode in index[split]:
                    folder = root / split / episode["name"]
                    # Private truth is read ONLY here, in the trusted test.
                    truth = json.loads((folder / "private/truth.json").read_text())
                    url = (address + "/api/findings?split=" + split +
                           "&episode=" + episode["name"])
                    with urlopen(url, timeout=10) as response:
                        payload = response.read()
                    actual = json.loads(payload)
                    assert actual["count"] == len(truth["issues"])
                    assert all("issue_id" not in row and
                               "expected_amount_minor" not in row
                               for row in actual["findings"])
                    if actual["count"]:
                        faulty += 1
                    else:
                        clean += 1
            assert faulty >= 12 and clean >= 2
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_dashboard_rejects_symlinked_summary_before_serving(tmp_path):
    root, _ = _dataset(tmp_path)
    summary = root / "evaluation" / "summary.json"
    outside = tmp_path / "outside-summary.json"
    outside.write_bytes(summary.read_bytes())
    summary.unlink()
    summary.symlink_to(outside)
    with pytest.raises(OSError, match="linked or escaped"):
        dashboard_server(root, port=0)


def test_dashboard_fails_on_manifest_episode_id_mismatch(tmp_path):
    root, _ = _dataset(tmp_path)
    entry = root / "train" / "episode-00" / "public" / "manifest.json"
    manifest = json.loads(entry.read_text())
    manifest["episode_id"] = "incorrect-id"
    entry.write_text(json.dumps(manifest))
    with dashboard_server(root, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = "http://127.0.0.1:" + str(server.server_address[1])
            url = address + "/api/records?split=train&episode=episode-00&table=invoices&page=0"
            with pytest.raises(HTTPError) as exc:
                urlopen(url, timeout=10)
            assert exc.value.code == 400
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_optional_evaluator_research_aggregate_requires_matching_dataset(tmp_path):
    from ledgergym.research_report import analyse_development_dataset
    root, _ = _dataset(tmp_path)
    report_root = tmp_path / "research"
    research = analyse_development_dataset(root, report_root, trials=1)
    file = report_root / "research_summary.json"
    with dashboard_server(root, port=0, research_report=file) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = "http://127.0.0.1:" + str(server.server_address[1])
            with urlopen(address + "/api/research", timeout=10) as response:
                raw = response.read()
            data = json.loads(raw)
            assert data["status"] == "available"
            assert data["report"]["episodes"] == 20
            assert data["report"]["policies"]["reconciliation"]["tp"] == 42
            assert data["report"]["official_score_modified"] is False
            assert "dataset_index_sha256" not in data["report"]
            assert b'"truth"' not in raw and b'"issue_id"' not in raw
        finally:
            server.shutdown()
            thread.join(timeout=5)
    contents = json.loads(file.read_text())
    contents["dataset_index_sha256"] = "0" * 64
    tampered = tmp_path / "wrong-research.json"
    tampered.write_text(json.dumps(contents))
    with pytest.raises(ValueError, match="does not match"):
        dashboard_server(root, port=0, research_report=tampered)
