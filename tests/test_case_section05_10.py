"""FinTech case section 05 (declared tolerance) and section 10 (agent diagnostics)."""
import json

from ledgergym import agent_diagnostics, score
from ledgergym.company_world import build_company


def _episode():
    public, truth, _ = build_company(77, {"faults": {"duplicate_invoice": 1, "payment_allocation": 1}})
    return public, truth


def test_declared_amount_tolerance_is_exact_minor_units():
    assert score.AMOUNT_TOLERANCE_MINOR == 0
    public, truth = _episode()
    ids = score.accessible_evidence_ids(public)
    issue = truth["issues"][0]

    def finding(amount):
        return {"type": issue["type"], "affected_ids": issue["affected_ids"], "claimed_amount_minor": amount,
                "currency": issue["currency"], "evidence_ids": issue["allowed_evidence_sets"][0], "explanation": ""}
    exact = score.evaluate([issue], [finding(issue["expected_amount_minor"])], ids, 0)
    off_by_one = score.evaluate([issue], [finding(issue["expected_amount_minor"] + 1)], ids, 0)
    assert (exact["tp"], exact["fp"]) == (1, 0)
    assert (off_by_one["tp"], off_by_one["fp"], off_by_one["fn"]) == (0, 1, 1)


def test_diagnostics_report_precision_recall_f1_return_steps_time(tmp_path, capsys):
    out = tmp_path / "diag.json"
    agent_diagnostics.main(["--held-out", "3", "--json", str(out)])
    report = json.loads(out.read_text())
    assert set(report["held_out"]) == set(agent_diagnostics.POLICIES)
    for row in report["held_out"].values():
        for key in ("precision", "recall", "mean_f1", "mean_return", "mean_steps", "mean_seconds",
                    "missed_by_type", "false_positives_by_claimed_type"):
            assert key in row
    assert report["held_out"]["oracle"]["mean_f1"] == 1
    assert report["held_out"]["mark_all"]["mean_return"] == -1
    assert "| reconciliation |" in capsys.readouterr().out


def _oracle(issues):
    return [{"type": i["type"], "affected_ids": i["affected_ids"], "claimed_amount_minor": i["expected_amount_minor"],
             "currency": i["currency"], "evidence_ids": i["allowed_evidence_sets"][0], "explanation": ""}
            for i in issues]


def _mark_all(public):
    return [{"type": kind, "affected_ids": [inv["invoice_id"]], "claimed_amount_minor": inv["total_minor"],
             "currency": inv["currency"], "evidence_ids": [inv["doc_id"]], "explanation": ""}
            for inv in public["tables"]["invoices"] for kind in sorted(score.TYPES)][:30]


def test_case_section05_reward_properties():
    """The five statements the case (section 05) asks the tests to show."""
    faulty_public, faulty = build_company(91, {"faults": {"duplicate_invoice": 1, "payment_allocation": 1,
                                                          "fx_rate_or_date": 1, "reporting_period": 1},
                                              "compounds": {"fx_allocation": 1}})[:2]
    clean_public, clean = build_company(92, {})[:2]
    f_ids, c_ids = score.accessible_evidence_ids(faulty_public), score.accessible_evidence_ids(clean_public)
    reward = lambda issues, findings, ids, steps=10: score.evaluate(issues, findings, ids, steps)["reward"]
    correct = _oracle(faulty["issues"])

    # 1. A complete correct answer with evidence beats silence on faulty books.
    assert reward(faulty["issues"], correct, f_ids) > reward(faulty["issues"], [], f_ids)
    # 2. Silence beats false accusations on clean books.
    accusation = _oracle(faulty["issues"])[:1]
    accusation[0]["affected_ids"] = [clean_public["tables"]["invoices"][0]["invoice_id"]]
    accusation[0]["evidence_ids"] = [clean_public["tables"]["invoices"][0]["doc_id"]]
    assert reward(clean["issues"], [], c_ids) > reward(clean["issues"], accusation, c_ids)
    # 3. Duplicates bring no gain.
    assert reward(faulty["issues"], correct + correct, f_ids) < reward(faulty["issues"], correct, f_ids)
    # 4. Marking every row/type gives a bad result, on faulty and on clean books.
    assert reward(faulty["issues"], _mark_all(faulty_public), f_ids) <= -0.9
    assert reward(clean["issues"], _mark_all(clean_public), c_ids) == -1
    # 5. Saving steps only slightly separates equal answers.
    cheap, costly = reward(faulty["issues"], correct, f_ids, 5), reward(faulty["issues"], correct, f_ids, 50)
    assert 0 < cheap - costly <= 0.1 and costly > 0.8
