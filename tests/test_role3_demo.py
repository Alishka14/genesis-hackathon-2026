import json
import subprocess
import sys

from role3_fixture import write_case


def test_local_demo_external_file_trace(tmp_path):
    root = tmp_path / "episode"
    write_case(root)
    trace = tmp_path / "trajectories.jsonl"
    run = subprocess.run([sys.executable, "-m", "ledgergym.role3_demo", "local",
                          "--episode", str(root), "--trajectory", str(trace)],
                         capture_output=True, text=True, check=True)
    result = json.loads(run.stdout)
    assert result["status"] == "VERIFIED_PASS" and result["replay"] == "exact"
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [row["action"]["name"] for row in rows] == ["list_records", "get_document", "calculator", "submit"]
    assert rows[-1]["terminated"] and rows[-1]["reward"] == 0 and result["score"]["return"] == .994
