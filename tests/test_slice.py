from ledgergym.world import make_episode
from ledgergym.env import LedgerSandbox
from ledgergym.score import evaluate


def test_seed_reproducible_and_truth_evidenced():
    public, truth = make_episode(42, fault=True)
    assert (public, truth) == make_episode(42, fault=True)
    assert len(truth["issues"]) == 1
    issue = truth["issues"][0]
    public_ids = {v for table in public["tables"].values() for row in table for k, v in row.items() if k.endswith("_id") and isinstance(v, str)}
    assert set(issue["allowed_evidence_sets"][0]) <= public_ids


def test_investigate_submit_score_end_to_end():
    public, truth = make_episode(42, fault=True)
    ids = {v for table in public["tables"].values() for row in table for k, v in row.items() if k.endswith("_id") and isinstance(v, str)}
    def evaluator(findings, steps):
        return evaluate(truth["issues"], findings, ids, steps)
    env = LedgerSandbox(public, evaluator)
    obs, info = env.reset()
    assert obs["remaining_steps"] == 100
    obs, reward, terminated, truncated, info = env.step({"action": "list_records", "table": "invoices", "limit": 50})
    assert reward == 0 and not terminated and not truncated
    assert len(obs["records"]) >= 2
    issue = truth["issues"][0]
    finding = {"type": issue["type"], "affected_ids": issue["affected_ids"], "claimed_amount_minor": issue["expected_amount_minor"], "currency": issue["currency"], "evidence_ids": issue["allowed_evidence_sets"][0], "explanation": "supported"}
    obs, reward, terminated, truncated, info = env.step({"action": "submit", "episode_id": public["manifest"]["episode_id"], "findings": [finding]})
    assert terminated and not truncated and reward == 0.998
    assert info["score"]["tp"] == 1


def test_calculator_decimal_and_input_attacks():
    public, truth = make_episode(7)
    env = LedgerSandbox(public, lambda findings, steps: {"reward": 0})
    env.reset()
    obs, _, _, _, _ = env.step({"action": "calculator", "expression": "0.1 + 0.2"})
    assert obs["value"] == "0.3"
    for expression in ("__import__('os').system('id')", "2**100000", "1/0"):
        obs, _, _, _, _ = env.step({"action": "calculator", "expression": expression})
        assert obs["error"] == "invalid_action"


def test_cursor_cannot_be_reused_for_a_different_table():
    public, truth = make_episode(7)
    env = LedgerSandbox(public, lambda findings, steps: {"reward": 0})
    env.reset()
    obs, _, _, _, _ = env.step({"action": "list_records", "table": "invoices", "limit": 1})
    cursor = obs["next_cursor"]
    assert cursor is not None
    obs, _, _, _, _ = env.step({"action": "list_records", "table": "ledger", "cursor": cursor, "limit": 1})
    assert obs["error"] == "invalid_action"


def test_closed_mode_hides_score_and_unknown_truth_table():
    public, truth = make_episode(7)
    env = LedgerSandbox(public, lambda findings, steps: {"reward": .6, "private": "secret"}, closed=True)
    env.reset()
    obs, reward, _, _, info = env.step({"action": "list_records", "table": "truth"})
    assert obs["error"] == "invalid_action" and "secret" not in repr((obs, info))
    obs, reward, terminated, truncated, info = env.step({"action": "submit", "episode_id": public["manifest"]["episode_id"], "findings": []})
    assert reward == 0 and info == {} and terminated and not truncated


def test_step_budget_and_submit_on_step_100():
    public, truth = make_episode(7, fault=False)
    calls = []
    def evaluator(findings, steps):
        calls.append((findings, steps))
        return {"reward": 1 - steps * .002}
    env = LedgerSandbox(public, evaluator)
    env.reset()
    for _ in range(99):
        obs, reward, terminated, truncated, _ = env.step({"action": "unknown"})
        assert reward == 0 and not terminated and not truncated
    obs, reward, terminated, truncated, _ = env.step({"action": "submit", "episode_id": public["manifest"]["episode_id"], "findings": []})
    assert terminated and not truncated and calls == [([], 99)]
    env.reset()
    for _ in range(100):
        obs, reward, terminated, truncated, _ = env.step({"action": "unknown"})
    assert truncated and not terminated and calls[-1] == ([], 100)


def test_malformed_submit_is_terminal_without_scoring():
    public, _ = make_episode(7)
    def forbidden(*args):
        raise AssertionError("malformed submit reached evaluator")
    env = LedgerSandbox(public, forbidden)
    env.reset()
    _, reward, terminated, truncated, _ = env.step({"action": "submit", "episode_id": public["manifest"]["episode_id"], "findings": [None]})
    assert (reward, terminated, truncated) == (-1, True, False)


def test_each_invoice_has_balanced_postings_and_duplicate_is_publicly_identifiable():
    for fault in (True, False):
        public, truth = make_episode(9, fault=fault)
        invoices = public["tables"]["invoices"]
        ledger = public["tables"]["ledger"]
        for invoice in invoices:
            postings = [row for row in ledger if row["invoice_id"] == invoice["invoice_id"]]
            assert len(postings) == 2
            assert sum(x["debit_minor"] for x in postings) == invoice["total_minor"]
            assert sum(x["credit_minor"] for x in postings) == invoice["total_minor"]
        assert (invoices[0]["line_items"] == invoices[1]["line_items"]) is fault
