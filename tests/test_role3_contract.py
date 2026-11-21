import json
import random
import subprocess
import sys

import pytest

import judge_adapter as judge
from role3_fixture import write_case


def action(name, **args):
    return {"name": name, "args": args}


def config(root, mode="closed"):
    return {"mode": mode, "episode_dir": str(root), "team_config": {}}


def checked(env, a, remaining, *, fail=False):
    obs, reward, terminated, truncated, info = env.step(a)
    json.dumps([obs, reward, terminated, truncated, info], allow_nan=False)
    assert type(terminated) is type(truncated) is bool
    assert type(reward) in (float, int) and reward == 0 and info == {}
    assert set(obs) == {"result", "error", "remaining_steps"}
    assert obs["remaining_steps"] == remaining
    if fail:
        assert obs["result"] is None and set(obs["error"]) == {"code", "message"}
        assert len(json.dumps(obs["error"])) < 180
    else:
        assert obs["error"] is None
    return obs["result"], terminated, truncated


def test_C01_C02_C03_C04_C05_C06_external_pages(tmp_path):
    answer, tables = write_case(tmp_path, large=True)
    env = judge.make_env()
    initial, info = env.reset(999, config(tmp_path))
    assert info == {} and set(initial) == {"task", "manifest", "policy", "remaining_steps"}
    assert initial["task"] and initial["remaining_steps"] == 100
    assert initial["manifest"] == json.loads((tmp_path / "public/manifest.json").read_text())
    assert initial["manifest"]["record_counts"]["ledger"] == len(tables["ledger"])
    assert initial["manifest"]["episode_id"] == answer["episode_id"]
    assert initial["policy"] == json.loads((tmp_path / "public/policy.json").read_text())
    assert "SECRET" not in json.dumps(initial)
    cursor = None
    rows = []
    for n in range(3):
        a = action("list_records", table="ledger", cursor=cursor, limit=50)
        page, t, tr = checked(env, a, 99 - 2*n)
        assert not t and not tr and 0 < len(page["records"]) <= 50
        again, _, _ = checked(env, a, 98 - 2*n)
        assert again == page
        rows.extend(page["records"])
        cursor = page["next_cursor"]
    assert cursor is None and rows == tables["ledger"]


def test_C07_C08_C09_C10_C11_C12_C13_C14_C15(tmp_path):
    answer, tables = write_case(tmp_path)
    env = judge.make_env()
    env.reset(123, config(tmp_path))
    row = tables["ledger"][0]
    doc = tables["invoices"][0]
    get = action("get_record", table="ledger", id=row["row_id"])
    got, _, _ = checked(env, get, 99)
    assert got == row
    got["row_id"] = "mutated copy"
    assert checked(env, action("get_document", doc_id=doc["doc_id"]), 98)[0] == doc
    assert checked(env, action("calculator", expression="0.1+0.2"), 97)[0] == "0.3"
    for n, a in enumerate([action("calculator", expression="unknown(1)"),
                           action("get_record", table="ledger", id="absent"),
                           action("get_document", doc_id="../private/truth.json"),
                           action("unknown"), action("list_records", table="private")]):
        checked(env, a, 96 - n, fail=True)
    assert checked(env, get, 91)[0] == row
    assert checked(env, action("submit", findings=answer), 90) == ({"accepted": True}, True, False)
    with pytest.raises(RuntimeError):
        env.step(get)
    assert env.final_score == {"tp": 0, "fp": 0, "fn": 0, "precision": 0., "recall": 0.,
                               "f1": 1., "return": .982}


@pytest.mark.parametrize("submit", [True, False], ids=["C16", "C17"])
def test_budget_boundaries(tmp_path, submit):
    answer, _ = write_case(tmp_path, 7)
    env = judge.make_env()
    env.reset(5, config(tmp_path))
    for left in range(99, 0, -1):
        checked(env, action("invalid"), left, fail=True)
    if submit:
        assert checked(env, action("submit", findings=answer), 0) == ({"accepted": True}, True, False)
        assert env.final_score["tp"] == 1 and env.final_score["return"] == pytest.approx(.802)
    else:
        assert env.step(action("invalid"))[2:4] == (False, True)
        assert env.final_score["tp"] == 0 and env.final_score["fn"] == 1
    with pytest.raises(RuntimeError):
        env.step(action("submit", findings=answer))


def test_C18_reset_clock_includes_file_loading(tmp_path, monkeypatch):
    from ledgergym import canonical
    answer, _ = write_case(tmp_path, 7)
    clock = [1000.]
    original_prepare = canonical._prepare
    def delayed_prepare(*args):
        result = original_prepare(*args)
        clock[0] += 60
        return result
    monkeypatch.setattr(canonical.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(canonical, "_prepare", delayed_prepare)
    env = judge.make_env()
    with pytest.raises(TimeoutError):
        env.reset(5, config(tmp_path))
    with pytest.raises(RuntimeError):
        env.step(action("submit", findings=answer))
    assert env.final_score["fn"] == 1


@pytest.mark.parametrize("mode", ["train", "closed"])
def test_C19_evaluator_score_and_malformed_submit(tmp_path, mode, caplog):
    answer, _ = write_case(tmp_path, 8)
    env = judge.make_env()
    env.reset(91, config(tmp_path, mode))
    checked(env, action("invalid"), 99, fail=True)
    obs, reward, t, tr, info = env.step(action("submit", findings=answer))
    assert obs == {"result": {"accepted": True}, "error": None, "remaining_steps": 98}
    expected = {"tp": 1, "fp": 0, "fn": 0, "precision": 1., "recall": 1., "f1": 1., "return": .998}
    assert judge.score_episode(str(tmp_path), answer, 1) == env.final_score == expected
    assert reward == (0 if mode == "closed" else .998) and t and not tr and info == {}
    env.reset(91, config(tmp_path, mode))
    obs, reward, t, tr, info = env.step(action("submit", findings=[]))
    assert obs["result"] is None and obs["error"] and t and not tr and info == {}
    assert reward == (0 if mode == "closed" else -1)
    invalid = judge.score_episode(str(tmp_path), [], 0)
    assert invalid == {key: -1 if key == "return" else None for key in expected}
    assert caplog.records and "SECRET" not in caplog.text


def test_C20_public_surface(tmp_path):
    for ix in (1, 7):
        root = tmp_path / str(ix)
        _, tables = write_case(root, ix)
        env = judge.make_env()
        results = [env.reset(987654321, config(root))]
        for table, rows in tables.items():
            results.append(env.step(action("list_records", table=table)))
            for row in rows:
                if "doc_id" in row:
                    results.append(env.step(action("get_document", doc_id=row["doc_id"])))
        for a in [action("get_document", doc_id=str(root / "private/truth.json")),
                  action("shell"), action("sql"), action("network"), action("list_records", table="provenance")]:
            results.append(env.step(a))
        trace = json.dumps(results)
        for secret in ("SECRET", "hidden-", "987654321", "truth", "provenance", "Traceback", "private", '"seed"'):
            assert secret not in trace


def test_generate_and_train(tmp_path):
    target = tmp_path / "episode"
    cfg = {"scenario": "duplicate_invoice", "fault": False}
    assert judge.generate_episode(221, cfg, str(target)) is None
    assert (target / "private/provenance.json").is_file()
    env = judge.make_env()
    expected = env.reset(221, config(target, "train"))
    assert env.reset(221, {"mode": "train", "team_config": cfg}) == expected


def test_external_fx_natural_id_and_inaccessible_evidence(tmp_path):
    answer, tables = write_case(tmp_path, 7)
    (tmp_path / "public/fx.csv").write_text(
        "date,source_currency,target_currency,rate\n2026-01-31,USD,KZT,497.0100\n", encoding="utf-8")
    env = judge.make_env()
    env.reset(1, config(tmp_path))
    assert checked(env, action("get_record", table="fx", id="2026-01-31:USD:KZT"), 99)[0] == {
        "date": "2026-01-31", "source_currency": "USD", "target_currency": "KZT", "rate": "497.0100"}
    answer["findings"][0]["evidence_ids"].append(tables["ledger"][0]["entity_id"])
    env.step(action("submit", findings=answer))
    assert env.final_score == judge.score_episode(tmp_path, answer, 1)
    assert env.final_score["fp"] == env.final_score["fn"] == 1


def test_cursor_reset_table_and_literal_replay_other_process(tmp_path):
    answer, _ = write_case(tmp_path, 6)
    cfg = config(tmp_path)
    env = judge.make_env()
    env.reset(551, cfg)
    first = action("list_records", table="ledger", limit=1, cursor=None)
    page = env.step(first)
    cursor = page[0]["result"]["next_cursor"]
    nxt = action("list_records", table="ledger", limit=1, cursor=cursor)
    wrong = action("list_records", table="invoices", limit=1, cursor=cursor)
    actions = [nxt, first, wrong, nxt, action("submit", findings=answer)]
    env.reset(551, cfg)
    steps = [env.step(a) for a in actions]
    assert steps[0][0]["error"] and steps[2][0]["error"]
    assert steps[1][0]["result"] == page[0]["result"] and steps[3][0]["error"] is None
    program = """import json, sys, judge_adapter
cfg, actions = json.load(sys.stdin)
env = judge_adapter.make_env()
env.reset(551, cfg)
print(json.dumps([[env.step(a) for a in actions], env.final_score]))
"""
    run = subprocess.run([sys.executable, "-c", program], text=True, capture_output=True,
                         input=json.dumps([cfg, actions]), check=True)
    assert json.loads(run.stdout) == json.loads(json.dumps([steps, env.final_score]))


def test_failed_reset_invalidates_and_sanitizes(tmp_path):
    write_case(tmp_path)
    env = judge.make_env()
    env.reset(1, config(tmp_path))
    (tmp_path / "public/ledger.csv").unlink()
    with pytest.raises(ValueError, match="^invalid episode$") as exc:
        env.reset(1, config(tmp_path))
    assert exc.value.__cause__ is None and env.final_score is None
    with pytest.raises(RuntimeError):
        env.step(action("list_records", table="ledger"))


def test_private_labels_in_external_public_data_are_rejected(tmp_path):
    write_case(tmp_path)
    policy = tmp_path / "public/policy.json"
    policy.write_text(json.dumps({"rounding": {"provenance": "untrusted sentinel"}}))
    with pytest.raises(ValueError, match="^invalid episode$"):
        judge.make_env().reset(29, config(tmp_path))


def test_oversize_and_nested_inputs_are_bounded(tmp_path):
    write_case(tmp_path)
    env = judge.make_env()
    env.reset(2, config(tmp_path))
    nested = []
    for _ in range(1500):
        nested = [nested]
    for n, value in enumerate([{"unknown": nested}, action("get_document", doc_id="x" * 100_000),
                               action("unknown", payload=list(range(8000))), float("inf")]):
        checked(env, value, 99 - n, fail=True)


def test_stateful_bounded_repetitions(tmp_path):
    answer, tables = write_case(tmp_path)
    def trial():
        rng = random.Random(491)
        env = judge.make_env()
        stream = []
        for _ in range(12):
            stream.append(env.reset(0, config(tmp_path)))
            prior = None
            for i in range(1, 101):
                a = rng.choice([action("list_records", table="ledger", limit=1, cursor=prior),
                                action("get_record", table="ledger", id=tables["ledger"][0]["row_id"]),
                                action("get_document", doc_id=tables["invoices"][0]["doc_id"]),
                                action("calculator", expression="4/2"), action("unknown"),
                                action("submit", findings=answer)])
                obs, reward, t, tr, info = step = env.step(a)
                stream.append(step)
                assert obs["remaining_steps"] == 100-i and reward == 0 and info == {}
                if isinstance(obs["result"], dict) and "next_cursor" in obs["result"]:
                    prior = obs["result"]["next_cursor"]
                if t or tr:
                    with pytest.raises(RuntimeError):
                        env.step(a)
                    break
        return json.dumps(stream, allow_nan=False)
    assert trial() == trial()
