"""Offline bundle integrity and release-gate contracts, no network required."""
import hashlib
import json

import pytest

from scripts import verify_bundle, verify_offline_release


def _bundle(root):
    root.mkdir()
    payload = root / "README.md"
    payload.write_text("LedgerGym test fixture\n")
    files = {"README.md": hashlib.sha256(payload.read_bytes()).hexdigest()}
    (root / "SHA256SUMS.json").write_text(json.dumps({
        "format": "ledgergym-offline-bundle-v1",
        "version": "0.1.0.dev16", "files": files,
    }))
    return files


def test_verified_bundle_has_exact_inventory(tmp_path):
    root = tmp_path / "bundle"
    _bundle(root)
    result = verify_bundle.verify_bundle(root)
    assert result["verified_files"] == 1
    assert result["version"] == "0.1.0.dev16"


@pytest.mark.parametrize("attack", [
    "edited_file", "deleted_file", "unlisted_file", "symlink_file",
    "traversal", "invalid_digest", "invalid_manifest", "symlink_directory",
])
def test_bundle_integrity_rejects_tampering(tmp_path, attack):
    root = tmp_path / "bundle"
    expected = _bundle(root)
    if attack == "edited_file":
        (root / "README.md").write_text("changed")
    elif attack == "deleted_file":
        (root / "README.md").unlink()
    elif attack == "unlisted_file":
        (root / "extra").write_text("not in manifest")
    elif attack == "symlink_file":
        (root / "README.md").unlink()
        (root / "README.md").symlink_to(tmp_path / "outside")
    elif attack == "symlink_directory":
        (root / "some-link").symlink_to(tmp_path, target_is_directory=True)
    else:
        item = json.loads((root / "SHA256SUMS.json").read_text())
        if attack == "traversal":
            item["files"] = {"../escape": next(iter(expected.values()))}
        elif attack == "invalid_digest":
            item["files"]["README.md"] = "not-sha256"
        elif attack == "invalid_manifest":
            item["format"] = "unrecognized"
        (root / "SHA256SUMS.json").write_text(json.dumps(item))
    with pytest.raises((ValueError, OSError)):
        verify_bundle.verify_bundle(root)


def test_installed_tests_require_nonempty_unskipped_passes(tmp_path):
    xml = tmp_path / "tests.xml"
    xml.write_text('<testsuite><testcase classname="unit" name="a"/></testsuite>')
    assert verify_offline_release._checked_installed_tests(xml) == {
        "executed": 1, "failed": 0, "skipped": 0
    }
    xml.write_text('<testsuite><testcase name="a"><skipped/></testcase></testsuite>')
    with pytest.raises(ValueError):
        verify_offline_release._checked_installed_tests(xml)
    xml.write_text('<testsuite><testcase name="a"><failure/></testcase></testsuite>')
    with pytest.raises(ValueError):
        verify_offline_release._checked_installed_tests(xml)
    xml.write_text('<testsuite></testsuite>')
    with pytest.raises(ValueError):
        verify_offline_release._checked_installed_tests(xml)


def test_installed_demo_requires_exact_replay():
    assert verify_offline_release._assert_demo(
        '{"status":"VERIFIED_PASS","replay":"exact"}') == {
            "status": "VERIFIED_PASS", "replay": "exact"
        }
    with pytest.raises(ValueError):
        verify_offline_release._assert_demo('{"status":"NOT_RUN","replay":"exact"}')


def test_installed_development_dataset_requires_full_replay():
    payload = {"train": 10, "dev": 10,
               "replay": {"trajectories": 60, "score_matches": 60}}
    assert verify_offline_release._assert_dataset(json.dumps(payload)) == {
        "train": 10, "dev": 10, "replayed_trajectories": 60
    }
    payload["replay"]["score_matches"] = 59
    with pytest.raises(ValueError):
        verify_offline_release._assert_dataset(json.dumps(payload))


def test_offline_release_rejects_existing_bundle_without_overwriting(monkeypatch, tmp_path):
    # Test the early output-safety check independent of local Python version.
    monkeypatch.setattr(verify_offline_release.sys, "version_info", (3, 11, 0))
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    output = tmp_path / "bundle"
    output.mkdir()
    marker = output / "must_preserve"
    marker.write_text("keep")
    with pytest.raises(ValueError, match="new"):
        verify_offline_release.verify_offline_release(
            wheels, output, tmp_path / "report.json")
    assert marker.read_text() == "keep"
    assert not (tmp_path / "report.json").exists()
