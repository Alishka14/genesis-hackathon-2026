"""LG-010 integration-level contract tests, not competition acceptance suite."""
import json
import unittest

from integration_reference.smoke import (
    MAX_STEPS, ReferenceEnvironment, _calculate, demo, generate_fixture, official_score,
)


class ReferenceTests(unittest.TestCase):
    def test_demo_is_scored_correctly(self):
        result = demo(seed=7)
        self.assertTrue(result["terminated"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["inspection_steps"], 3)
        self.assertEqual(result["score"]["tp"], 1)
        self.assertAlmostEqual(result["reward"], 0.994)

    def test_seed_reproducibility_and_balance(self):
        pub1, tru1 = generate_fixture(10)
        pub2, tru2 = generate_fixture(10)
        self.assertEqual((pub1, tru1), (pub2, tru2))
        self.assertEqual(sum(r["debit_minor"] for r in pub1["ledger"]), sum(r["credit_minor"] for r in pub1["ledger"]))

    def test_clean_silent_case(self):
        _, truth = generate_fixture(12, duplicate=False)
        self.assertEqual(truth, [])
        self.assertEqual(official_score([], truth, 0)["reward"], 1)
        bad = {"type": "duplicate_invoice", "affected_ids": ["guess"], "claimed_amount_minor": 5,
               "currency": "KZT", "evidence_ids": [], "explanation": "unconfirmed"}
        self.assertEqual(official_score([bad], truth, 0)["reward"], -1)

    def test_no_truth_in_agent_json(self):
        env = ReferenceEnvironment()
        obs, info = env.reset(15)
        pub = json.dumps({"obs": obs, "info": info}, sort_keys=True)
        self.assertNotIn("private-issue", pub)
        self.assertNotIn("allowed_evidence_sets", pub)
        seen, _, _, _, inf = env.step({"type": "list_records", "table": "invoices", "limit": 50})
        self.assertNotIn("allowed_evidence_sets", json.dumps([seen, inf]))

    def test_duplicate_findings_are_fp(self):
        public, truth = generate_fixture(5)
        inv = public["invoices"]
        finding = {"type": "duplicate_invoice", "affected_ids": [i["invoice_id"] for i in inv],
                   "claimed_amount_minor": 125_000, "currency": "KZT",
                   "evidence_ids": [i["doc_id"] for i in inv], "explanation": "duplicate"}
        score = official_score([finding, finding], truth, 10)
        self.assertEqual((score["tp"], score["fp"], score["fn"]), (1, 1, 0))
        self.assertAlmostEqual(score["reward"], 2 / 3 * 2 - 1 - 0.02)

    def test_missing_evidence_fails(self):
        pub, truth = generate_fixture(5)
        inv = pub["invoices"]
        f = {"type": "duplicate_invoice", "affected_ids": [i["invoice_id"] for i in inv],
             "claimed_amount_minor": 125_000, "currency": "KZT", "evidence_ids": [inv[0]["doc_id"]],
             "explanation": "incomplete"}
        result = official_score([f], truth, 0)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))

    def test_invalid_inputs_spend_a_step(self):
        env = ReferenceEnvironment()
        env.reset(1)
        obs, reward, term, trunc, info = env.step({"type": "get_document", "doc_id": "../truth.json"})
        self.assertEqual(obs["error"], "unknown_id")
        self.assertEqual(obs["remaining_steps"], MAX_STEPS - 1)
        self.assertEqual((reward, term, trunc), (0.0, False, False))

    def test_terminal_budget(self):
        env = ReferenceEnvironment()
        env.reset(3)
        for _ in range(MAX_STEPS - 1):
            env.step({"type": "invalid"})
        obs, reward, term, trunc, info = env.step({"type": "invalid"})
        self.assertTrue(trunc)
        self.assertFalse(term)
        self.assertEqual(info, {"findings": []})
        self.assertEqual(obs["status"], "budget_exhausted")

    def test_hundredth_submit_is_allowed(self):
        env = ReferenceEnvironment(duplicate=False)
        obs, _ = env.reset(4)
        for _ in range(MAX_STEPS - 1):
            env.step({"type": "invalid"})
        _, score, term, trunc, info = env.step({"type": "submit", "episode_id": obs["manifest"]["episode_id"], "findings": []})
        self.assertTrue(term)
        self.assertFalse(trunc)
        self.assertAlmostEqual(score, 1 - 0.002 * (MAX_STEPS - 1))

    def test_decimal_calculator_rejects_code(self):
        self.assertEqual(_calculate("0.1 + 0.2"), "0.3")
        for payload in ["__import__('os')", "1 / 0", "pow(2,3)", "a+1", "1**1000"]:
            with self.subTest(payload=payload), self.assertRaises((ValueError, SyntaxError)):
                _calculate(payload)

    def test_invalid_submit_is_minus_one(self):
        env = ReferenceEnvironment()
        env.reset(4)
        _, rew, term, trunc, info = env.step({"type": "submit", "findings": [{"type": "fake"}]})
        self.assertEqual(rew, -1)
        self.assertTrue(term)
        self.assertEqual(info["error"], "malformed_submit")


if __name__ == "__main__":
    unittest.main()
