"""Contract tests for the aggregate P0 local verification command.

No real Docker/CI/bundle operations occur here: these tests exercise the
aggregator's validation and fail-closed behavior, not full release readiness.
"""
import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scripts import verify_p0_release as gate


def _offline_success():
    return {
        "success": True,
        "stages": {
            stage: {"status": "pass"} for stage in gate.REQUIRED_OFFLINE_STAGES
        },
    }


def test_offline_subgate_requires_exact_installed_stage_coverage():
    report = _offline_success()
    report["stages"]["installed_wheel_tests"]["metrics"] = {
        "executed": 50, "failed": 0, "skipped": 0}
    report["stages"]["verify_manifest"]["verified_files"] = 150
    metrics = gate._validate_offline(report)
    assert metrics == {
        "verified_stages": 10, "installed_tests": 50,
        "verified_bundle_files": 150,
    }
    del report["stages"]["installed_dashboard_assets"]
    with pytest.raises(ValueError, match="stage coverage"):
        gate._validate_offline(report)


@pytest.mark.parametrize("mutated", [
    {"executed": 44, "failed": 0, "skipped": 0},
    {"executed": 50, "failed": 1, "skipped": 0},
    {"executed": 50, "failed": 0, "skipped": 1},
])
def test_offline_subgate_fails_on_insufficient_or_skipped_tests(mutated):
    report = _offline_success()
    report["stages"]["installed_wheel_tests"]["metrics"] = mutated
    with pytest.raises(ValueError, match="installed wheel test"):
        gate._validate_offline(report)


def test_real_docker_junit_never_accepts_skips(tmp_path):
    valid = tmp_path / "docker.xml"
    root = ElementTree.Element("testsuite")
    for _ in range(22):
        ElementTree.SubElement(root, "testcase")
    ElementTree.ElementTree(root).write(valid)
    assert gate._check_junit(valid, minimum=22) == {
        "executed": 22, "failed": 0, "skipped": 0}
    ElementTree.SubElement(root[0], "skipped")
    ElementTree.ElementTree(root).write(valid)
    with pytest.raises(ValueError, match="skipped"):
        gate._check_junit(valid, minimum=22)


def test_focused_gate_reports_technical_success_but_not_contest_success(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(gate, "_source_provenance", lambda: {
        "status": "pass", "clean_checkout": True, "commit": "a" * 40})
    monkeypatch.setattr(gate.shutil, "which", lambda name: "/bin/node")
    seen = []
    def fake_run(label, command, *, timeout):
        seen.append((label, tuple(command)))
        return {"status": "pass", "exit_code": 0, "duration_sec": 0.01}
    monkeypatch.setattr(gate, "_run", fake_run)
    report = tmp_path / "focused.json"
    assert gate.run(mode="focused", wheelhouse=None, bundle=None,
                    report_path=report, timeout=5) == 0
    data = json.loads(report.read_text())
    assert data["success"] is True
    assert data["submission_ready"] is False
    assert data["contest_certified"] is False
    assert data["human_signoff"] == "pending"
    assert [name for name, _ in seen] == ["frontend_js_syntax", "source_tests"]
    with pytest.raises(FileExistsError):
        gate.run(mode="focused", wheelhouse=None, bundle=None,
                 report_path=report, timeout=5)


def test_focused_gate_fails_closed_if_node_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "_source_provenance", lambda: {
        "status": "pass", "clean_checkout": True, "commit": "b" * 40})
    monkeypatch.setattr(gate.shutil, "which", lambda name: None)
    monkeypatch.setattr(gate, "_run", lambda *a, **k: {
        "status": "pass", "exit_code": 0, "duration_sec": 0.01})
    report = tmp_path / "missing-node.json"
    assert gate.run(mode="focused", wheelhouse=None, bundle=None,
                    report_path=report, timeout=5) == 1
    data = json.loads(report.read_text())
    assert data["success"] is False
    assert data["stages"]["frontend_js_syntax"]["status"] == "not_verified"


def test_full_mode_needs_pinned_wheels_and_output_path(tmp_path):
    with pytest.raises(ValueError, match="wheelhouse"):
        gate.run(mode="full", wheelhouse=None, bundle=None,
                 report_path=tmp_path / "gate.json", timeout=5)
    assert not (tmp_path / "gate.json").exists()
