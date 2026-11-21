"""P0: full development events and local dashboard public-only boundary."""
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

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
            for bad_url, expected in (
                ("/private/truth.json", 404),
                ("/api/records?split=train&episode=../../private&table=ledger&page=0", 400),
                ("/api/records?split=train&episode=" + entry
                 + "&table=private&page=0", 400),
                ("/api/records?split=train&episode=" + entry
                 + "&table=ledger&page=0&extra=1", 400),
                ("/api/records?split=train&episode=" + entry
                 + "&table=ledger&page=1001", 400),
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
