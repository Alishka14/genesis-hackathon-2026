"""One-command local P0 technical preflight for the LedgerGym release stack.

Runs source integration, strict real Docker test evidence, JS parser,
offline installed-wheel gate and measured resource profile on a clean checkout.
Does NOT merge PRs, grant judge access, or certify organizer's hidden tests.

Requires a prepared 8-wheel hash-locked wheelhouse for --mode full.
The Python running this script must have pytest installed; Python 3.11 is used
separately by the offline wheel builder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DOCKER_TESTS = ("tests/test_isolated_runner.py", "tests/test_role3_runtime.py")
FRONTEND_TESTS = ("tests/test_dashboard_and_full_events.py", "tests/test_resource_profile.py",
                  "tests/test_p0_release_gate.py",
                  "tests/test_research_diagnostics.py",
                  "tests/test_research_robustness.py",
                  "tests/test_cab_invariance.py",
                  "tests/test_cab_company_pairs.py",
                  "tests/test_research_report.py",
                  "tests/test_replay.py")
REQUIRED_OFFLINE_STAGES = {
    "build_dependencies", "build_bundle", "verify_manifest",
    "installed_runtime", "installed_dashboard_assets", "installed_dev_dependencies",
    "pip_check", "installed_wheel_tests", "installed_demo", "installed_10plus10",
}


def _run(label: str, command: list[str], *, timeout: int) -> dict:
    start = time.monotonic()
    print(f"[p0:{label}] running", flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                check=False, timeout=timeout)
        status = "pass" if result.returncode == 0 else "fail"
        if result.returncode != 0:
            # Keep stdout/stderr out of the aggregate shareable JSON.
            print((result.stdout + "\n" + result.stderr)[-3500:], file=sys.stderr)
        return {"status": status, "exit_code": result.returncode,
                "duration_sec": round(time.monotonic() - start, 3)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[p0:{label}] {type(exc).__name__}", file=sys.stderr)
        return {"status": "not_verified", "exit_code": None,
                "failure_type": type(exc).__name__,
                "duration_sec": round(time.monotonic() - start, 3)}


def _require_json(path: Path, *, truth_field: str = "success") -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get(truth_field) is not True:
        raise ValueError("subreport was not verified")
    return value


def _check_junit(path: Path, *, minimum: int) -> dict:
    tree = ElementTree.parse(path)
    cases = list(tree.iter("testcase"))
    if len(cases) < minimum:
        raise ValueError("insufficient testcases")
    if any(
        case.find("skipped") is not None
        or case.find("failure") is not None
        or case.find("error") is not None for case in cases
    ):
        raise ValueError("at least one Docker testcase failed or was skipped")
    return {"executed": len(cases), "failed": 0, "skipped": 0}


def _source_provenance() -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise ValueError("unexpected source commit")
    # Do not reveal untracked sensitive filenames to shareable reports.
    return {"status": "pass" if not status else "fail",
            "clean_checkout": not bool(status), "commit": sha}


def _validate_offline(report: dict) -> dict:
    stages = report.get("stages", {})
    if (not isinstance(stages, dict) or set(stages) != REQUIRED_OFFLINE_STAGES
            or any(not isinstance(stage, dict) or stage.get("status") != "pass"
                   for stage in stages.values())):
        raise ValueError("offline verification stage coverage incomplete")
    tests = stages["installed_wheel_tests"].get("metrics", {})
    if (tests.get("executed", 0) < 45 or tests.get("failed") != 0
            or tests.get("skipped") != 0):
        raise ValueError("installed wheel test metrics invalid")
    return {"verified_stages": len(stages),
            "installed_tests": tests["executed"],
            "verified_bundle_files": stages["verify_manifest"].get("verified_files")}


def run(*, mode: str, wheelhouse: Path | None, bundle: Path | None,
        report_path: Path, timeout: int = 1200) -> int:
    if mode not in {"focused", "full"} or timeout < 1:
        raise ValueError("invalid verification mode or timeout")
    if mode == "full" and (wheelhouse is None or bundle is None):
        raise ValueError("full mode needs --wheelhouse and --bundle")
    report_path = Path(report_path).expanduser().resolve()
    if report_path.exists():
        raise FileExistsError("report exists: choose a new report path")
    report = {
        "gate": "ledgergym-p0-local-handoff-v1",
        "mode": mode,
        "python": ".".join(map(str, sys.version_info[:3])),
        "success": False,
        "contest_certified": False,
        "submission_ready": False,
        "docker_isolation_covered": False,
        "official_resource_limits_verified": False,
        "human_signoff": "pending",
        "stages": {},
    }
    stages = report["stages"]

    with tempfile.TemporaryDirectory(prefix="ledgergym-p0-") as tmp:
        temp = Path(tmp)
        try:
            try:
                stages["source_provenance"] = _source_provenance()
            except (OSError, subprocess.CalledProcessError, ValueError):
                stages["source_provenance"] = {"status": "not_verified"}

            node = shutil.which("node")
            if node is None:
                stages["frontend_js_syntax"] = {
                    "status": "not_verified", "reason": "node_missing"}
            else:
                stages["frontend_js_syntax"] = _run(
                    "frontend_js_syntax",
                    [node, "--check", str(ROOT / "ledgergym/dashboard_static/app.js")],
                    timeout=min(60, timeout),
                )

            if mode == "focused":
                stages["source_tests"] = _run(
                    "source_tests",
                    [sys.executable, "-m", "pytest", "-q", "-rs",
                     "-p", "no:cacheprovider", *FRONTEND_TESTS],
                    timeout=timeout,
                )
            else:
                integration_report = temp / "integration.json"
                stages["integration"] = _run(
                    "integration",
                    [sys.executable, str(ROOT / "scripts/verify_integration.py"),
                     "--mode", "full", "--report", str(integration_report),
                     "--timeout", str(timeout)],
                    timeout=timeout * 4,
                )
                if stages["integration"]["status"] == "pass":
                    try:
                        gate = _require_json(integration_report)
                        required = {"tracked_private_files", "pytest",
                                    "mixed_generator", "causal_pairs"}
                        if not required <= set(gate.get("stages", {})):
                            raise ValueError("integration stages missing")
                        if any(gate["stages"][name]["status"] != "pass"
                               for name in required):
                            raise ValueError("integration subgate not green")
                        stages["integration"]["metrics"] = {
                            "episodes": gate["stages"]["mixed_generator"]["metrics"]["episodes"],
                            "replayed_trajectories": gate["stages"]["mixed_generator"]["metrics"]["replayed_trajectories"],
                            "causal_pairs": gate["stages"]["causal_pairs"]["metrics"]["paired_comparisons"],
                        }
                    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
                        stages["integration"]["status"] = "fail"

                docker_xml = temp / "docker-tests.xml"
                stages["docker_isolation"] = _run(
                    "docker_isolation",
                    [sys.executable, "-m", "pytest", "-q", "-rs",
                     "-p", "no:cacheprovider", "--junitxml", str(docker_xml),
                     *DOCKER_TESTS],
                    timeout=timeout,
                )
                if stages["docker_isolation"]["status"] == "pass":
                    try:
                        stages["docker_isolation"]["metrics"] = _check_junit(
                            docker_xml, minimum=22)
                        report["docker_isolation_covered"] = True
                    except (ValueError, OSError, ElementTree.ParseError):
                        stages["docker_isolation"]["status"] = "fail"

                # Run through the original independently verified 3.11 offline
                # builder. The new release must prove HTML/CSS/JS are in wheel.
                python311 = shutil.which("python3.11")
                if python311 is None:
                    stages["offline_wheel"] = {
                        "status": "not_verified", "reason": "python311_missing"}
                else:
                    offline_report = temp / "offline.json"
                    stages["offline_wheel"] = _run(
                        "offline_wheel",
                        [python311, str(ROOT / "scripts/verify_offline_release.py"),
                         "--wheelhouse", str(wheelhouse),
                         "--bundle", str(bundle),
                         "--report", str(offline_report),
                         "--timeout", str(timeout)],
                        timeout=timeout * 12,
                    )
                    if stages["offline_wheel"]["status"] == "pass":
                        try:
                            gate = _require_json(offline_report)
                            stages["offline_wheel"]["metrics"] = _validate_offline(gate)
                        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
                            stages["offline_wheel"]["status"] = "fail"

                # An observation only, *not* a proof of any judge resource cap.
                resource_json = temp / "resource.json"
                dataset = temp / "resource-dataset"
                stages["resource_observation"] = _run(
                    "resource_observation",
                    [sys.executable, str(ROOT / "scripts/profile_local_resources.py"),
                     "--timeout", str(timeout), "--report", str(resource_json),
                     "--", sys.executable, "-m", "ledgergym.company_dataset",
                     str(dataset), "--seed", "2026",
                     "--settlement-hard-negatives", "--evaluate"],
                    timeout=timeout + 30,
                )
                if stages["resource_observation"]["status"] == "pass":
                    try:
                        value = json.loads(resource_json.read_text(encoding="utf-8"))
                        if (value.get("status") != "pass"
                                or value.get("contest_certified") is not False
                                or value.get("resources_enforced") is not False):
                            raise ValueError("resource evidence was overstated")
                        stages["resource_observation"]["metrics"] = {
                            "elapsed_sec": value["elapsed_sec"],
                            "user_cpu_sec": value["user_cpu_sec"],
                            "system_cpu_sec": value["system_cpu_sec"],
                            "peak_child_rss_mib_observed": value["peak_child_rss_mib_observed"],
                        }
                    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                        stages["resource_observation"]["status"] = "fail"

            report["success"] = all(stage["status"] == "pass"
                                    for stage in stages.values())
            return 0 if report["success"] else 1
        finally:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, sort_keys=True,
                                              indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
            print(json.dumps({"technical_pass": report["success"], "mode": mode,
                              "report": str(report_path),
                              "submission_ready": False}, sort_keys=True),
                  flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("focused", "full"), default="focused")
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    try:
        return run(mode=args.mode, wheelhouse=args.wheelhouse,
                   bundle=args.bundle, report_path=args.report,
                   timeout=args.timeout)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
