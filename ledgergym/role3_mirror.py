"""Test-only mirror. Run from a checkout with pytest installed."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.etree import ElementTree


def _status(case):
    if case.find("skipped") is not None:
        return "NOT_RUN"
    if case.find("failure") is not None or case.find("error") is not None:
        return "CONFIRMED_FAIL"
    return "VERIFIED_PASS"


def _aggregate(statuses):
    if "CONFIRMED_FAIL" in statuses:
        return "CONFIRMED_FAIL"
    if not statuses or "NOT_RUN" in statuses:
        return "NOT_RUN"
    return "VERIFIED_PASS"


def run():
    root = Path(__file__).resolve().parents[1]
    files = ["tests/test_role3_contract.py", "tests/test_role3_pairs.py", "tests/test_role3_runtime.py",
             "tests/test_role3_review.py"]
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "results.xml"
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               *files, f"--junitxml={output}"], cwd=root,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not output.is_file():
            raise RuntimeError("pytest mirror did not produce results")
        cases = {case.attrib["name"]: _status(case) for case in ElementTree.parse(output).iter("testcase")}
    def status(*names):
        return _aggregate([cases.get(name, "NOT_RUN") for name in names])
    checks = {}
    for n in range(1, 16):
        grouped = ("test_C01_C02_C03_C04_C05_C06_external_pages" if n <= 6
                   else "test_C07_C08_C09_C10_C11_C12_C13_C14_C15")
        checks[f"C{n:02d}"] = status(grouped)
    for n in (16, 17):
        checks[f"C{n}"] = status(f"test_budget_boundaries[C{n}]")
    checks["C18"] = status("test_C18_reset_clock_includes_file_loading",
                           "test_reset_interrupts_blocked_public_load",
                           "test_real_pipe_faults[import time; time.sleep(5)-timeout]")
    checks["C19"] = status("test_C19_evaluator_score_and_malformed_submit[closed]",
                           "test_C19_evaluator_score_and_malformed_submit[train]")
    boundary = [f"test_container_boundary_and_cleanup[{kind}]" for kind in
                ("submit", "crash", "timeout", "malformed", "train_file", "train_generated", "missing_image")]
    checks["C20"] = status("test_C20_public_surface", "test_mount_and_limits", *boundary)
    pairs = {f"P{n:02d}": status(f"test_paired_transport[P{n:02d}]") for n in range(1, 21)}
    if proc.returncode != 0:
        sys.stderr.buffer.write(proc.stdout)
    return {"contract": checks, "paired_transport_only": pairs,
            "C20_public_surface": status("test_C20_public_surface"),
            "C20_docker": status(*boundary)}, proc.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional evaluator-side JSON report")
    args = parser.parse_args()
    report, rc = run()
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
