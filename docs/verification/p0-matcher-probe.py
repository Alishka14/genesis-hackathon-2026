"""Read-only matcher diagnostics on a file-fed synthetic episode (trusted side)."""
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import judge_adapter
from ledgergym import score
from role3_fixture import write_case


def inspect_case(path):
    envelope, tables = write_case(path, number=6)
    original = envelope["findings"][0]
    entity = tables["invoices"][0]["entity_id"]
    env = judge_adapter.make_env()
    env.reset(6, {"mode": "closed", "episode_dir": str(path)})
    # A visible foreign key has no retrievable record or document of its own.
    lookups = [{"name": "get_record", "args": {"table": t, "id": entity}} for t in tables]
    lookups.append({"name": "get_document", "args": {"doc_id": entity}})
    assert all(env.step(request)[0]["error"] for request in lookups)
    valid = (1, 0, 0)
    mismatch = (0, 1, 1)
    cases = [
        ("repeated_affected", "affected_ids", original["affected_ids"] * 2, valid),
        ("repeated_evidence", "evidence_ids", original["evidence_ids"] * 2, valid),
        ("unknown_type", "type", "unlisted", mismatch),
        ("currency_case", "currency", "kzt", mismatch),
        ("accessible_extra", "evidence_ids", original["evidence_ids"] + [tables["payments"][0]["doc_id"]], valid),
        ("unaddressable_extra", "evidence_ids", original["evidence_ids"] + [entity], mismatch),
    ]
    results = {}
    for label, field, value, expected in cases:
        sub = copy.deepcopy(envelope)
        sub["findings"][0][field] = value
        metrics = judge_adapter.score_episode(path, sub, 0)
        actual = tuple(metrics[k] for k in ("tp", "fp", "fn"))
        results[label] = {"expected": expected, "actual": actual, "status": "PASS" if actual == expected else "FAIL"}
    # Inspect the actual assignment before the production evaluator discards it.
    truth_path = path / "private/truth.json"
    issue = json.loads(truth_path.read_text(encoding="utf-8"))["issues"][0]
    truth_path.write_text(json.dumps({"issues": [dict(issue, issue_id=k) for k in ("A", "B")]}), encoding="utf-8")
    observed = {}
    def capture(frame, event, arg):
        if event == "return" and frame.f_code is score.evaluate.__code__:
            observed.update({frame.f_locals["issues"][j]["issue_id"]: i for j, i in frame.f_locals["paired"].items()})
    prior = sys.getprofile()
    try:
        sys.setprofile(capture)
        metrics = judge_adapter.score_episode(path, dict(envelope, findings=[original, original]), 0)
    finally:
        sys.setprofile(prior)
    expected = {"A": 0, "B": 1}
    results["M11"] = {"expected": expected, "actual": observed, "tp": metrics["tp"],
                      "status": "PASS" if observed == expected else "FAIL"}
    # The native evaluator admits every top-level *_id, including entity references.
    from ledgergym.generator import generate_episode
    from ledgergym.runtime import create_episode
    config = {"scenario": "duplicate_invoice", "fault": True}
    native_public, native_score = create_episode(6, config)
    _, native_truth = generate_episode(6, config)
    native_issue = native_truth["issues"][0]
    native_extra = native_public["tables"]["invoices"][0]["entity_id"]
    generated = path / "native-comparison"
    judge_adapter.generate_episode(6, config, generated)
    sub = {"episode_id": native_public["manifest"]["episode_id"], "findings": [{
        "type": native_issue["type"], "currency": native_issue["currency"],
        "affected_ids": native_issue["affected_ids"], "claimed_amount_minor": native_issue["expected_amount_minor"],
        "evidence_ids": native_issue["allowed_evidence_sets"][0] + [native_extra], "explanation": "probe"}]}
    for label, metrics in (("native_entity_reference", native_score(sub["findings"], 0)),
                           ("canonical_same_reference", judge_adapter.score_episode(generated, sub, 0))):
        actual = tuple(metrics[k] for k in ("tp", "fp", "fn"))
        results[label] = {"expected": mismatch, "actual": actual, "status": "PASS" if actual == mismatch else "FAIL"}

    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(inspect_case(Path(tmp)), indent=2))
