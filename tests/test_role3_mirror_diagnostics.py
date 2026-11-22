"""Regression: role3_mirror must explain a missing pytest instead of a bare traceback."""
from ledgergym import role3_mirror


def test_missing_pytest_is_reported_as_not_run_without_spawning(monkeypatch, capsys):
    real_find_spec = role3_mirror.importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        return None if name == "pytest" else real_find_spec(name, *args, **kwargs)

    def forbidden_run(*args, **kwargs):
        raise AssertionError("mirror must not start pytest when it is missing")

    monkeypatch.setattr(role3_mirror.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(role3_mirror.subprocess, "run", forbidden_run)
    monkeypatch.setattr("sys.argv", ["role3_mirror"])
    assert role3_mirror.main() == 2
    err = capsys.readouterr().err
    assert "NOT_RUN" in err and "pytest is not installed" in err
    assert "requirements-role3-test.txt" in err


def test_missing_junit_reports_pytest_output_tail(monkeypatch):
    class Finished:
        returncode = 4
        stdout = b"line1\nERROR: file or directory not found: tests/x.py\n"

    monkeypatch.setattr(role3_mirror.subprocess, "run", lambda *a, **k: Finished())
    try:
        role3_mirror.run()
    except RuntimeError as exc:
        assert "did not produce results" in str(exc)
        assert "file or directory not found" in str(exc)
    else:
        raise AssertionError("a missing JUnit report must not be treated as success")
