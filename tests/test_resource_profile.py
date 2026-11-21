"""Portable contracts for optional local resource telemetry."""
import json
from pathlib import Path
import sys

import pytest

from scripts import profile_local_resources


@pytest.mark.skipif(sys.platform not in ("darwin", "linux"),
                    reason="Unix rusage child telemetry only")
def test_resource_profile_records_success_and_nonsecret_metrics(tmp_path):
    target = tmp_path / "profile.json"
    status = profile_local_resources.profile(
        [sys.executable, "-c", "print('internal-only-message')"],
        timeout=10,
        report_path=target,
    )
    assert status == 0
    report = json.loads(target.read_text())
    assert report["status"] == "pass"
    assert report["exit_code"] == 0
    assert report["elapsed_sec"] >= 0
    assert report["user_cpu_sec"] >= 0
    assert report["peak_child_rss_mib_observed"] >= 0
    assert report["network_isolation_enforced"] is False
    assert report["contest_certified"] is False
    assert report["resources_enforced"] is False
    assert "internal-only-message" not in target.read_text()
    with pytest.raises(FileExistsError):
        profile_local_resources.profile(
            [sys.executable, "-c", "print(1)"], timeout=5,
            report_path=target,
        )


@pytest.mark.skipif(sys.platform not in ("darwin", "linux"),
                    reason="Unix rusage child telemetry only")
def test_resource_profile_fails_closed_on_nonzero_command(tmp_path):
    target = tmp_path / "failed.json"
    status = profile_local_resources.profile(
        [sys.executable, "-c", "raise SystemExit(5)"],
        timeout=10, report_path=target,
    )
    assert status == 1
    report = json.loads(target.read_text())
    assert report["status"] == "fail"
    assert report["exit_code"] == 5


def test_resource_profile_rejects_invalid_settings_without_output(tmp_path):
    report = tmp_path / "invalid.json"
    with pytest.raises(ValueError):
        profile_local_resources.profile([], timeout=1, report_path=report)
    with pytest.raises(ValueError):
        profile_local_resources.profile(
            [sys.executable], timeout=0, report_path=report)
    with pytest.raises(ValueError):
        profile_local_resources.profile(
            [sys.executable], timeout=5, report_path=report,
            memory_limit=-1,
        )
    assert not report.exists()
