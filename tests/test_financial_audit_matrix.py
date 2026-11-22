"""Reproducible 700-world / 1500-check financial matrix, plus proofs it can fail."""
import copy
from datetime import datetime, timedelta, timezone
import json

from ledgergym.company_world import build_company
from ledgergym.financial_audit_matrix import CONFIGS, check_world, main, run_matrix


def test_full_matrix_700_worlds_1500_checks_pass():
    report = run_matrix(range(100))
    assert report["worlds"] == 700
    assert report["checks"] == {"balance": 700, "duplicate_invoice": 200, "payment_allocation": 300,
                                "fx_rate_or_date": 200, "reporting_period": 100}
    assert report["total_checks"] == 1500
    assert report["failed"] == 0 and report["success"] is True


def _world(kind, seed=3):
    return build_company(seed, CONFIGS[kind])[:2]


def _failed(public, truth):
    return [name for name, ok, _ in check_world(public, truth) if not ok]


def test_tampered_expected_amount_is_detected_for_every_fault_type():
    # Unlike a truth-vs-inspect_company comparison (enforced inside build_company),
    # this recomputation must reject a truth amount that public facts do not support.
    for kind in ("duplicate_invoice", "payment_allocation", "fx_rate_or_date", "reporting_period"):
        public, truth = _world(kind)
        assert _failed(public, truth) == []
        bad = copy.deepcopy(truth)
        bad["issues"][0]["expected_amount_minor"] += 1
        assert _failed(public, bad) == [kind], kind


def test_unbalanced_ledger_is_detected():
    public, truth = _world("clean")
    public = copy.deepcopy(public)
    public["tables"]["ledger"][0]["debit_minor"] += 1
    assert "balance" in _failed(public, truth)


def test_fx_fault_with_recorded_rate_of_correct_day_is_not_confirmed():
    public, truth = _world("fx_rate_or_date")
    public = copy.deepcopy(public)
    payment_id = next(x for x in truth["issues"][0]["affected_ids"]
                      if any(p["payment_id"] == x for p in public["tables"]["payments"]))
    payment = next(p for p in public["tables"]["payments"] if p["payment_id"] == payment_id)
    zone = timezone(timedelta(hours=5))
    day = datetime.fromisoformat(payment["timestamp"]).astimezone(zone).date().isoformat()
    correct = next(r for r in public["tables"]["fx"] if r["date"] == day)
    for row in public["tables"]["ledger"]:
        if row["payment_id"] == payment_id:
            row["rate_id"] = correct["rate_id"]
    # Recorded amount no longer matches the recorded rate's day rule: claim rejected.
    assert _failed(public, truth) == ["fx_rate_or_date"]


def test_cli_exit_code_and_report(tmp_path, capsys):
    out = tmp_path / "matrix.json"
    assert main(["--seeds", "2", "--report", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["worlds"] == 14 and report["success"] is True
    assert json.loads(capsys.readouterr().out)["total_checks"] == report["total_checks"]


def test_varied_matrix_700_worlds_1500_checks_pass():
    from ledgergym.financial_audit_matrix import VARIED
    report = run_matrix(range(100), options=VARIED)
    assert report["worlds"] == 700 and report["total_checks"] == 1500
    assert report["failed"] == 0 and report["options"] == VARIED
