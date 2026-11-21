"""Agent-visible reader and pagination contract, independent of generator truth."""
import copy
import pytest

from ledgergym.env import LedgerSandbox


@pytest.fixture
def public():
    return {
        "manifest": {"episode_id": "contract-example"},
        "policy": {},
        "tables": {
            "ledger": [{"row_id": f"row-{i}", "debit_minor": i} for i in range(103)],
            "invoices": [{"invoice_id": "inv-1", "doc_id": "doc-1"}],
            "payments": [{"payment_id": "pay-1", "doc_id": "doc-2"}],
            "fx": [{"rate_id": "rate-1", "date": "2026-01-10", "rate": "450.00"}],
        },
    }


@pytest.fixture
def env(public):
    sandbox = LedgerSandbox(public, lambda findings, steps: {"reward": 0})
    sandbox.reset()
    return sandbox


@pytest.mark.parametrize("table", ["truth", "provenance", "debug", "../../private"])
def test_unapproved_table_stays_inaccessible_even_if_loader_supplies_it(public, table):
    public["tables"][table] = [{"row_id": "hidden-sentinel", "secret": "private-sentinel"}]
    sandbox = LedgerSandbox(public, lambda findings, steps: {"reward": 0}, closed=True)
    sandbox.reset()
    for action in (
        {"action": "list_records", "table": table},
        {"action": "get_record", "table": table, "id": "hidden-sentinel"},
    ):
        observation, reward, terminated, truncated, info = sandbox.step(action)
        assert observation.get("error") == "invalid_action"
        assert "sentinel" not in repr((observation, info))
        assert reward == 0 and not terminated and not truncated and info == {}
    assert observation["remaining_steps"] == 98


@pytest.mark.parametrize("table,record_id", [
    ("ledger", "row-0"), ("invoices", "inv-1"),
    ("payments", "pay-1"), ("fx", "rate-1"),
])
def test_public_record_can_be_retrieved_by_its_primary_id(env, public, table, record_id):
    observation, reward, terminated, truncated, _ = env.step({
        "action": "get_record", "table": table, "id": record_id,
    })
    assert observation.get("record") == public["tables"][table][0]
    assert reward == 0 and not terminated and not truncated


def test_reset_invalidates_previously_issued_cursor(env):
    first = env.step({"action": "list_records", "table": "ledger", "limit": 50})[0]
    old_cursor = first["next_cursor"]
    assert old_cursor is not None
    initial, _ = env.reset()
    assert initial["remaining_steps"] == 100
    observation = env.step({"action": "list_records", "table": "ledger", "cursor": old_cursor})[0]
    assert observation.get("error") == "invalid_action"
    assert observation["remaining_steps"] == 99


def test_cursor_from_another_environment_is_not_accepted(env, public):
    cursor = env.step({"action": "list_records", "table": "ledger"})[0]["next_cursor"]
    other = LedgerSandbox(public, lambda findings, steps: {"reward": 0})
    other.reset()
    observation = other.step({"action": "list_records", "table": "ledger", "cursor": cursor})[0]
    assert observation.get("error") == "invalid_action"


@pytest.mark.parametrize("cursor", ["contract-example:ledger:50", "unknown", 50, [], {}])
def test_unissued_cursor_is_rejected_without_echoing_input(env, cursor):
    observation = env.step({"action": "list_records", "table": "ledger", "cursor": cursor})[0]
    assert observation == {"error": "invalid_action", "remaining_steps": 99}


def test_cursor_stays_bound_to_its_table(env):
    cursor = env.step({"action": "list_records", "table": "ledger"})[0]["next_cursor"]
    observation = env.step({"action": "list_records", "table": "invoices", "cursor": cursor})[0]
    assert observation.get("error") == "invalid_action"


def test_pagination_covers_every_row_once_and_same_cursor_repeats_same_page(env):
    action = {"action": "list_records", "table": "ledger", "limit": 50}
    first = env.step(action)[0]
    again = env.step(action)[0]
    assert again["records"] == first["records"]
    assert again["next_cursor"] == first["next_cursor"]
    second = env.step(dict(action, cursor=first["next_cursor"]))[0]
    third = env.step(dict(action, cursor=second["next_cursor"]))[0]
    assert [len(page["records"]) for page in (first, second, third)] == [50, 50, 3]
    assert third["next_cursor"] is None
    assert [r["row_id"] for page in (first, second, third) for r in page["records"]] == [f"row-{i}" for i in range(103)]


@pytest.mark.parametrize("action", [
    {"action": "list_records", "table": "ledger", "unexpected": True},
    {"action": "get_record", "table": "ledger", "id": "row-0", "path": "private"},
    {"action": "get_document", "doc_id": "doc-1", "table": "truth"},
    {"action": "calculator", "expression": "1+1", "shell": "ignored"},
])
def test_reader_rejects_unexpected_fields_and_still_consumes_one_step(env, action):
    observation, reward, terminated, truncated, info = env.step(action)
    assert observation == {"error": "invalid_action", "remaining_steps": 99}
    assert (reward, terminated, truncated, info) == (0, False, False, {})


def test_reading_does_not_expose_mutable_environment_state(env):
    action = {"action": "get_record", "table": "ledger", "id": "row-0"}
    first = env.step(action)[0]
    first["record"]["debit_minor"] = 999
    assert env.step(action)[0]["record"]["debit_minor"] == 0


def test_cursor_change_does_not_change_scoring_or_budget(public):
    from ledgergym.score import evaluate
    sandbox = LedgerSandbox(copy.deepcopy(public), lambda findings, steps: evaluate([], findings, set(), steps))
    sandbox.reset()
    first = sandbox.step({"action": "list_records", "table": "ledger"})[0]
    sandbox.step({"action": "list_records", "table": "ledger", "cursor": first["next_cursor"]})
    _, reward, terminated, truncated, info = sandbox.step({
        "action": "submit", "episode_id": "contract-example", "findings": [],
    })
    assert (reward, terminated, truncated) == (0.996, True, False)
    assert info["score"]["f1"] == 1
