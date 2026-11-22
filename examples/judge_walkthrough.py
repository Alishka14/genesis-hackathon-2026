"""Scripted agent walkthrough through the judge interface (demo, FinTech case §09).

Generates one synthetic company with four planted errors, then plays a simple
scripted auditor through JudgeEnv in closed mode: it can only use the five
tools, sees no truth, and receives reward 0 until the evaluator reveals the
frozen score at the end. Run: python examples/judge_walkthrough.py
"""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import judge_adapter  # noqa: E402
from ledgergym.company_checks import inspect_company  # noqa: E402
from ledgergym.canonical import JudgeEnv  # noqa: E402

CONFIG = {"postings": 400, "documents": 60,
          "faults": {"duplicate_invoice": 1, "payment_allocation": 1, "fx_rate_or_date": 1, "reporting_period": 1}}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        episode = Path(tmp) / "episode"
        judge_adapter.generate_episode(2026, CONFIG, episode)
        print(f"episode files: public/ -> agent   private/ -> evaluator only ({', '.join(sorted(p.name for p in (episode / 'private').iterdir()))})")

        env = JudgeEnv()
        obs, info = env.reset(0, {"mode": "closed", "episode_dir": str(episode)})
        m, policy = obs["manifest"], obs["policy"]
        print(f"reset: {m['episode_id'][:20]}..  {m['counts']}  base {m['base_currency']}  steps left {obs['remaining_steps']}")

        tables, step = {}, 0
        for table in ("invoices", "payments", "fx", "ledger"):
            rows, cursor, pages = [], None, 0
            while True:
                args = {"table": table, "limit": 50} | ({"cursor": cursor} if cursor else {})
                obs, reward, terminated, truncated, info = env.step({"name": "list_records", "args": args})
                step += 1
                pages += 1
                rows += obs["result"]["records"]
                cursor = obs["result"]["next_cursor"]
                if cursor is None:
                    break
            tables[table] = rows
            print(f"step {step:>2}  list_records {table:<8} {pages} page(s), {len(rows)} rows   reward {reward}")

        invoice = tables["invoices"][0]
        obs, reward, *_ = env.step({"name": "get_document", "args": {"doc_id": invoice["doc_id"]}})
        step += 1
        print(f"step {step:>2}  get_document {invoice['doc_id'][:14]}..  total {obs['result']['total_minor']} {obs['result']['currency']}")
        expression = "+".join(str(line["amount_minor"]) for line in invoice["line_items"])
        obs, reward, *_ = env.step({"name": "calculator", "args": {"expression": expression}})
        step += 1
        print(f"step {step:>2}  calculator   sum of lines = {obs['result']}  (matches total: {obs['result'] == str(invoice['total_minor'])})")
        obs, reward, *_ = env.step({"name": "get_record", "args": {"table": "ledger", "id": "no-such-row"}})
        step += 1
        print(f"step {step:>2}  get_record   unknown id -> error {obs['error']['code']!r}, step still spent ({obs['remaining_steps']} left)")

        findings = inspect_company({"manifest": m, "policy": policy, "tables": tables})
        for f in findings:
            print(f"   finding  {f['type']:<19} amount {f['claimed_amount_minor']:>9} {f['currency']}  evidence {len(f['evidence_ids'])} ids")
        obs, reward, terminated, truncated, info = env.step(
            {"name": "submit", "args": {"findings": {"episode_id": m["episode_id"], "findings": findings}}})
        step += 1
        print(f"step {step:>2}  submit {len(findings)} findings -> {obs['result']}  terminated={terminated}  reward to agent={reward}  info={info}")

        s = env.final_score
        print(f"evaluator only: TP {s['tp']}  FP {s['fp']}  FN {s['fn']}  P {s['precision']:.2f}  R {s['recall']:.2f}  "
              f"F1 {s['f1']:.2f}  return {s['return']:.3f}  (= 2*F1 - 1 - 0.002*{step - 1} steps)")


if __name__ == "__main__":
    main()
