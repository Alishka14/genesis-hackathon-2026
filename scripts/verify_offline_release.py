"""Build and verify LedgerGym's offline distribution in isolated venvs.

Requires Python 3.11, a pre-downloaded 8-wheel hash-locked wheelhouse, and a
new bundle path. This command does not download anything or use PyPI. It does
not enforce kernel-level network isolation or certify the organizer's tests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import venv
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
INSTALLED_TESTS = (
    "tests/test_score.py",
    "tests/test_company_settlements_v2.py",
    "tests/test_v2_independent_truth.py",
    "tests/test_v2_pair_dataset.py",
    # Exercise the dashboard and complete transition recorder *from the
    # installed wheel*, not a repo-imported ledgergym package.
    "tests/test_dashboard_and_full_events.py",
    "tests/test_replay.py",
    "tests/test_research_diagnostics.py",
    "tests/test_research_robustness.py",
    "tests/test_research_report.py",
    "tests/test_cab_invariance.py",
)


def _execute(label, argv, *, cwd, stages, timeout=600):
    print(f"[offline:{label}] running", flush=True)
    started = time.monotonic()
    try:
        run = subprocess.run(
            [str(arg) for arg in argv], cwd=cwd, capture_output=True,
            text=True, timeout=timeout, check=False,
        )
        code = run.returncode
        stdout = run.stdout
        if code != 0:
            print((stdout + "\n" + run.stderr)[-5500:], file=sys.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        code = -1
        stdout = ""
        print(f"[offline:{label}] {type(exc).__name__}", file=sys.stderr)
    stages[label] = {"status": "pass" if code == 0 else "fail",
                     "exit_code": code,
                     "duration_sec": round(time.monotonic() - started, 3)}
    if code != 0:
        raise RuntimeError(f"offline stage failed: {label}")
    return stdout


def _checked_installed_tests(path):
    root = ElementTree.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases or any(
        case.find("failure") is not None
        or case.find("error") is not None
        or case.find("skipped") is not None for case in cases
    ):
        raise ValueError("installed package tests were empty, failed or skipped")
    return {"executed": len(cases), "failed": 0, "skipped": 0}


def _assert_demo(stdout):
    data = json.loads(stdout)
    if data.get("status") != "VERIFIED_PASS" or data.get("replay") != "exact":
        raise ValueError("installed distribution demo did not replay")
    return {"status": "VERIFIED_PASS", "replay": "exact"}


def _assert_dataset(stdout):
    data = json.loads(stdout)
    if (data.get("train") != 10 or data.get("dev") != 10
            or data.get("replay") != {"trajectories": 60, "score_matches": 60}):
        raise ValueError("installed distribution dataset or replay differs")
    return {"train": 10, "dev": 10, "replayed_trajectories": 60}


def _venv_python(folder):
    venv.EnvBuilder(with_pip=True, clear=False).create(folder)
    if sys.platform == "win32":
        return folder / "Scripts" / "python.exe"
    return folder / "bin" / "python"


def verify_offline_release(wheelhouse, bundle, report_path, *, timeout=600):
    if sys.version_info[:2] != (3, 11):
        raise ValueError("offline bundle builder requires CPython 3.11")
    wheelhouse = Path(wheelhouse).expanduser().resolve(strict=True)
    bundle = Path(bundle).expanduser().resolve()
    report_path = Path(report_path).expanduser().resolve()
    if not wheelhouse.is_dir() or bundle.exists():
        raise ValueError("wheelhouse must exist and bundle output must be new")
    if timeout <= 0:
        raise ValueError("stage timeout must be positive")
    if report_path.is_relative_to(bundle):
        raise ValueError("report must live outside the immutable bundle directory")
    report = {
        "gate": "ledgergym-offline-installed-v1",
        "python": ".".join(map(str, sys.version_info[:3])),
        "stages": {}, "success": False,
        "package_isolation": "fresh_virtualenv_and_no_index_pip",
        "network_isolation_enforced": False,
        "docker_isolation_covered": False,
        "contest_certified": False,
    }
    stages = report["stages"]
    with tempfile.TemporaryDirectory(prefix="ledgergym-offline-verify-") as temporary:
        temp = Path(temporary)
        try:
            builder_py = _venv_python(temp / "builder-venv")
            _execute("build_dependencies", [
                builder_py, "-m", "pip", "install", "--no-index",
                "--only-binary=:all:", "--require-hashes", "--no-deps",
                "--find-links", wheelhouse,
                "-r", ROOT / "requirements-build.lock",
            ], cwd=temp, stages=stages, timeout=timeout)

            _execute("build_bundle", [
                builder_py, ROOT / "scripts" / "build_offline_bundle.py",
                wheelhouse, bundle,
            ], cwd=temp, stages=stages, timeout=timeout)
            try:
                result = json.loads(_execute("verify_manifest", [
                    builder_py, bundle / "verify_bundle.py",
                ], cwd=temp, stages=stages, timeout=timeout))
                if not isinstance(result.get("verified_files"), int) or result["verified_files"] < 20:
                    raise ValueError("manifest verified no meaningful file inventory")
                stages["verify_manifest"]["verified_files"] = result["verified_files"]
            except (ValueError, KeyError, TypeError):
                stages["verify_manifest"]["status"] = "fail"
                raise

            installed_py = _venv_python(temp / "installed-venv")
            _execute("installed_runtime", [
                installed_py, "-m", "pip", "install", "--no-index",
                "--only-binary=:all:", "--require-hashes", "--no-deps",
                "--find-links", bundle / "wheels",
                "-r", bundle / "requirements-runtime.lock",
            ], cwd=temp, stages=stages, timeout=timeout)
            _execute("installed_dashboard_assets", [
                installed_py, "-I", "-c",
                "from importlib.resources import files; "
                "from ledgergym.dashboard import dashboard_server; "
                "base=files('ledgergym').joinpath('dashboard_static'); "
                "assert all(base.joinpath(name).read_bytes() for name in "
                "('index.html','app.css','app.js'))",
            ], cwd=temp, stages=stages, timeout=timeout)
            _execute("installed_dev_dependencies", [
                installed_py, "-m", "pip", "install", "--no-index",
                "--only-binary=:all:", "--require-hashes", "--no-deps",
                "--find-links", bundle / "wheels",
                "-r", bundle / "requirements-dev.lock",
            ], cwd=temp, stages=stages, timeout=timeout)
            _execute("pip_check", [
                installed_py, "-m", "pip", "check",
            ], cwd=temp, stages=stages, timeout=timeout)

            test_report = temp / "installed-tests.xml"
            _execute("installed_wheel_tests", [
                installed_py, "-I", "-m", "pytest",
                "-q", "-p", "no:cacheprovider", "--import-mode=importlib",
                "--junitxml", test_report,
                *(bundle / name for name in INSTALLED_TESTS),
            ], cwd=temp, stages=stages, timeout=timeout)
            try:
                stages["installed_wheel_tests"]["metrics"] = _checked_installed_tests(test_report)
            except (ValueError, OSError, ElementTree.ParseError):
                stages["installed_wheel_tests"]["status"] = "fail"
                raise

            demo = _execute("installed_demo", [
                installed_py, "-I", "-m", "ledgergym.role3_demo", "local",
            ], cwd=temp, stages=stages, timeout=timeout)
            try:
                stages["installed_demo"]["metrics"] = _assert_demo(demo)
            except (ValueError, TypeError, json.JSONDecodeError):
                stages["installed_demo"]["status"] = "fail"
                raise

            dataset = _execute("installed_10plus10", [
                installed_py, "-I", "-m", "ledgergym.company_dataset",
                temp / "installed-dataset", "--seed", "2026", "--evaluate",
            ], cwd=temp, stages=stages, timeout=timeout)
            try:
                stages["installed_10plus10"]["metrics"] = _assert_dataset(dataset)
            except (ValueError, TypeError, json.JSONDecodeError):
                stages["installed_10plus10"]["status"] = "fail"
                raise
            report["success"] = True
        except Exception as exc:
            # Keep the report structured even on failed third-party subprocesses.
            print(f"Offline release NOT VERIFIED: {type(exc).__name__}: {exc}", file=sys.stderr)
            report["failure_type"] = type(exc).__name__
        finally:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"success": report["success"], "report": str(report_path),
                              "verified_stages": len(stages)}, sort_keys=True))
    return 0 if report["success"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True, help="new output directory")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600, help="per-stage timeout")
    args = parser.parse_args()
    try:
        return verify_offline_release(args.wheelhouse, args.bundle, args.report,
                                      timeout=args.timeout)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
