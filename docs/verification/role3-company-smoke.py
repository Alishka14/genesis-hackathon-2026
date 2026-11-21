"""Exercise the combined company generator and judge transport from a checkout."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import judge_adapter as judge
from ledgergym.episode_io import load_public_episode
from ledgergym.flight_recorder import FlightRecorder, verify_replay


FAULT_TYPES = ("duplicate_invoice", "payment_allocation", "fx_rate_or_date", "reporting_period")
COMPOUNDS = {"fx_allocation": 1, "duplicate_allocation": 1}
CASES = [
    ("clean", {"postings": 200, "documents": 20}, 0),
    ("faulty", {"postings": 400, "documents": 80, "faults": dict.fromkeys(FAULT_TYPES, 1)}, 4),
    ("compound", {"postings": 400, "documents": 80, "compounds": COMPOUNDS}, 4),
    ("large", {"postings": 2000, "documents": 200, "faults": dict.fromkeys(FAULT_TYPES, 2),
               "compounds": COMPOUNDS}, 12),
]


def action(name, **args):
    return {"name": name, "args": args}


def verify_case(path, company_config, expected):
    seed = 81
    judge.generate_episode(seed, {"scenario": "company", **company_config}, path)
    public = load_public_episode(path / "public")
    truth = json.loads((path / "private/truth.json").read_text(encoding="utf-8"))
    provenance = json.loads((path / "private/provenance.json").read_text(encoding="utf-8"))
    rows = public["tables"]["ledger"]
    invoice = public["tables"]["invoices"][0]
    assert provenance["seed"] == seed
    assert len(truth["issues"]) == expected
    assert len(rows) == company_config["postings"]
    assert len(public["tables"]["invoices"]) + len(public["tables"]["payments"]) == company_config["documents"]

    config = {"mode": "closed", "episode_dir": str(path)}
    recorder = FlightRecorder(judge.make_env())
    initial, info = recorder.reset(seed, config)
    assert info == {} and initial["manifest"] == public["manifest"]

    reads = [
        (action("list_records", table="ledger", limit=50), rows[:50]),
        (action("get_record", table="ledger", id=rows[0]["row_id"]), rows[0]),
        (action("get_document", doc_id=invoice["doc_id"]), invoice),
        (action("calculator", expression="0.1+0.2"), "0.3"),
    ]
    for request, expected_result in reads:
        obs, reward, terminated, truncated, info = recorder.step(request)
        assert (reward, terminated, truncated, info) == (0, False, False, {})
        assert obs["error"] is None
        actual = obs["result"]["records"] if request["name"] == "list_records" else obs["result"]
        assert actual == expected_result

    findings = [
        {
            "type": issue["type"],
            "affected_ids": issue["affected_ids"],
            "claimed_amount_minor": issue["expected_amount_minor"],
            "currency": issue["currency"],
            "evidence_ids": issue["allowed_evidence_sets"][0],
            "explanation": "Trusted synthetic oracle smoke",
        }
        for issue in truth["issues"]
    ]
    submit = {"episode_id": initial["manifest"]["episode_id"], "findings": findings}
    assert recorder.step(action("submit", findings=submit))[1:] == (0, True, False, {})
    score = judge.score_episode(path, submit, len(reads))
    replay_score = verify_replay(judge.make_env(), seed, config, initial, recorder.rows)
    assert score == recorder.final_score == replay_score
    assert (score["tp"], score["fp"], score["fn"], score["return"]) == (expected, 0, 0, 0.992)
    return {"postings": len(rows), "documents": company_config["documents"], "score": score, "replay": "exact"}


def main():
    with TemporaryDirectory() as temporary:
        for label, config, expected in CASES:
            result = verify_case(Path(temporary) / label, config, expected)
            print(json.dumps({"case": label, **result}))


if __name__ == "__main__":
    main()
