"""Measure a trusted local CLI run: wall time, CPU and peak child RSS.

Observational profiler for macOS/Linux. It does NOT enforce cgroup resource
limits, block networking, or certify the contest judge's hardware budget.
Use the Docker integration tests separately for agent isolation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
try:
    import resource
except ImportError:  # Windows: unavailable; fail gracefully if invoked.
    resource = None
import subprocess
import sys
import time


def profile(command, *, timeout, report_path, wall_limit=None, memory_limit=None):
    if not command or timeout <= 0:
        raise ValueError("expected a command and a positive timeout")
    if wall_limit is not None and wall_limit <= 0:
        raise ValueError("wall limit must be positive")
    if memory_limit is not None and memory_limit <= 0:
        raise ValueError("memory limit must be positive")
    if resource is None or not sys.platform.startswith(("darwin", "linux")):
        raise RuntimeError("resource profiling supports macOS/Linux only")
    report_path = Path(report_path).expanduser().resolve()
    if report_path.exists():
        raise FileExistsError("report path already exists; refusing overwrite")

    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    status = "error"
    returncode = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            returncode = process.wait(timeout=timeout)
            status = "pass" if returncode == 0 else "fail"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            status = "timeout"
    except OSError:
        status = "spawn_error"
    elapsed = time.monotonic() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    # Apple exposes ru_maxrss in bytes, Linux in KiB. The maximum is a
    # process-tree observation, not exact simultaneous aggregate memory.
    rss_mib = after.ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    report = {
        "gate": "ledgergym-local-resource-profile-v1",
        "status": status,
        "exit_code": returncode,
        "elapsed_sec": round(elapsed, 3),
        "user_cpu_sec": round(max(0.0, after.ru_utime - before.ru_utime), 3),
        "system_cpu_sec": round(max(0.0, after.ru_stime - before.ru_stime), 3),
        "peak_child_rss_mib_observed": round(rss_mib, 2),
        "max_wall_sec_configured": wall_limit,
        "max_memory_mib_configured": memory_limit,
        "resources_enforced": False,
        "network_isolation_enforced": False,
        "contest_certified": False,
    }
    if wall_limit is not None and elapsed > wall_limit:
        report["status"] = "limit_exceeded"
    if memory_limit is not None and rss_mib > memory_limit:
        report["status"] = "limit_exceeded"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "elapsed_sec": report["elapsed_sec"],
                      "peak_child_rss_mib_observed": report["peak_child_rss_mib_observed"]}))
    return 0 if report["status"] == "pass" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-wall", type=float)
    parser.add_argument("--max-memory", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return profile(command, timeout=args.timeout, report_path=args.report,
                       wall_limit=args.max_wall, memory_limit=args.max_memory)
    except (ValueError, FileExistsError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
