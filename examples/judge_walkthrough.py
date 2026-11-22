"""Scripted agent walkthrough through the judge interface (demo, FinTech case §09).

Generates one synthetic company with four planted errors, then plays a simple
scripted auditor through JudgeEnv in closed mode: it can only use the five
tools, sees no truth, and receives reward 0 until the evaluator reveals the
frozen score at the end.

    python examples/judge_walkthrough.py              # compact log
    python examples/judge_walkthrough.py --detailed   # every call and observation,
                                                      # train mode and attack policies

LEDGERGYM_DEMO_PAUSES (optional JSON {"section": seconds}) only adds pauses
between sections for screen recording; it does not change any result.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import judge_adapter  # noqa: E402
from ledgergym.company_checks import inspect_company  # noqa: E402
from ledgergym.canonical import JudgeEnv  # noqa: E402

CONFIG = {"postings": 400, "documents": 60,
          "faults": {"duplicate_invoice": 1, "payment_allocation": 1, "fx_rate_or_date": 1, "reporting_period": 1}}
PAUSES = json.loads(os.environ.get("LEDGERGYM_DEMO_PAUSES", "{}"))


def section(name, title, detailed):
    if detailed:
        print(f"\n── {title} " + "─" * max(4, 70 - len(title)), flush=True)


def pause(name):
    if name in PAUSES:
        time.sleep(float(PAUSES[name]))


def short(value, limit=110):
    text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    return text if len(text) <= limit else text[:limit - 3] + "..."


def scripted_audit(env, obs, detailed):
    """The scripted policy: read every table, check one document, then apply public rules."""
    m, policy = obs["manifest"], obs["policy"]
    tables, step = {}, 0
    section("read", "2. list_records: the policy reads every table page by page", detailed)
    for table in ("invoices", "payments", "fx", "ledger"):
        rows, cursor, pages = [], None, 0
        while True:
            args = {"table": table, "limit": 50} | ({"cursor": cursor} if cursor else {})
            action = {"name": "list_records", "args": args}
            obs, reward, terminated, truncated, info = env.step(action)
            step += 1
            pages += 1
            rows += obs["result"]["records"]
            cursor = obs["result"]["next_cursor"]
            if detailed and pages == 1:
                print(f"step {step:>2}  {short(action)}")
                print(f"         -> {len(obs['result']['records'])} records, next_cursor={'<token>' if cursor else None}, "
                      f"error={obs['error']}, remaining_steps={obs['remaining_steps']}, reward={reward}, terminated={terminated}")
            if cursor is None:
                break
        tables[table] = rows
        if detailed and pages > 1:
            print(f"   ...  {pages - 1} more page(s) of {table} through next_cursor  (steps {step - pages + 2}-{step})")
        elif not detailed:
            print(f"step {step:>2}  list_records {table:<8} {pages} page(s), {len(rows)} rows   reward {reward}")
    pause("read")

    section("tools", "3. get_document, calculator and a bad request", detailed)
    invoice = tables["invoices"][0]
    obs, reward, *_ = env.step({"name": "get_document", "args": {"doc_id": invoice["doc_id"]}})
    step += 1
    print(f"step {step:>2}  get_document {invoice['doc_id'][:14]}..  total {obs['result']['total_minor']} {obs['result']['currency']}"
          + (f", {len(obs['result']['line_items'])} line items" if detailed else ""))
    expression = "+".join(str(line["amount_minor"]) for line in invoice["line_items"])
    obs, reward, *_ = env.step({"name": "calculator", "args": {"expression": expression}})
    step += 1
    print(f"step {step:>2}  calculator   {expression if detailed else 'sum of lines'} = {obs['result']}  "
          f"(matches total: {obs['result'] == str(invoice['total_minor'])})")
    if detailed:
        bad = env.step({"name": "calculator", "args": {"expression": "__import__('os')"}})[0]
        step += 1
        print(f"step {step:>2}  calculator   __import__('os') -> error {bad['error']['code']!r}: only decimal arithmetic")
    obs, reward, *_ = env.step({"name": "get_record", "args": {"table": "ledger", "id": "no-such-row"}})
    step += 1
    print(f"step {step:>2}  get_record   unknown id -> error {obs['error']['code']!r}, step still spent ({obs['remaining_steps']} left)")
    pause("tools")

    section("findings", "4. the scripted policy applies public accounting rules", detailed)
    findings = inspect_company({"manifest": m, "policy": policy, "tables": tables})
    for f in findings:
        print(f"   finding  {f['type']:<19} amount {f['claimed_amount_minor']:>9} {f['currency']}  evidence {len(f['evidence_ids'])} ids"
              + (f"  affected {len(f['affected_ids'])} ids" if detailed else ""))
    pause("findings")
    return findings, step


def submit(env, episode_id, findings):
    return env.step({"name": "submit", "args": {"findings": {"episode_id": episode_id, "findings": findings}}})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scripted agent walkthrough through the judge interface.")
    parser.add_argument("--detailed", action="store_true", help="print every call and observation, then train mode and attacks")
    detailed = parser.parse_args(argv).detailed
    with tempfile.TemporaryDirectory() as tmp:
        episode = Path(tmp) / "episode"
        judge_adapter.generate_episode(2026, CONFIG, episode)
        section("reset", "1. generate_episode + reset: what the agent sees", detailed)
        if detailed:
            print(f"generate_episode(seed=2026, config={short(CONFIG, 150)})")
        print(f"episode files: public/ -> agent   private/ -> evaluator only ({', '.join(sorted(p.name for p in (episode / 'private').iterdir()))})")

        env = JudgeEnv()
        obs, info = env.reset(0, {"mode": "closed", "episode_dir": str(episode)})
        m = obs["manifest"]
        if detailed:
            print('reset(0, {"mode": "closed", "episode_dir": ...}) -> observation, info')
            print(f"   task: {obs['task']!r}")
            print(f"   manifest: {short({k: m[k] for k in ('episode_id', 'base_currency', 'period_start', 'period_end', 'counts')}, 160)}")
            print(f"   policy: {short(obs['policy'], 160)}")
            print(f"   remaining_steps: {obs['remaining_steps']}   info: {info}   (no truth, no seed, no file paths)")
            pause("reset")
        else:
            print(f"reset: {m['episode_id'][:20]}..  {m['counts']}  base {m['base_currency']}  steps left {obs['remaining_steps']}")

        findings, step = scripted_audit(env, obs, detailed)
        section("submit", "5. submit: closed mode, then the evaluator", detailed)
        obs, reward, terminated, truncated, info = submit(env, m["episode_id"], findings)
        step += 1
        print(f"step {step:>2}  submit {len(findings)} findings -> {obs['result']}  terminated={terminated}  reward to agent={reward}  info={info}")
        s = env.final_score
        print(f"evaluator only: TP {s['tp']}  FP {s['fp']}  FN {s['fn']}  P {s['precision']:.2f}  R {s['recall']:.2f}  "
              f"F1 {s['f1']:.2f}  return {s['return']:.3f}  (= 2*F1 - 1 - 0.002*{step - 1} steps)")
        pause("submit")

        if detailed:
            section("contrast", "6. train mode and attempts to game the reward", detailed)
            train = JudgeEnv()
            train.reset(0, {"mode": "train", "episode_dir": str(episode)})
            r = submit(train, m["episode_id"], findings)[1]
            print(f"train mode, same findings, 0 inspection steps -> reward returned to the agent: {r}")
            invoices = env_tables_invoices(episode)
            attacks = {
                "mark all (4 types x every invoice)": [
                    {"type": kind, "affected_ids": [i["invoice_id"]], "claimed_amount_minor": i["total_minor"],
                     "currency": i["currency"], "evidence_ids": [i["doc_id"]], "explanation": ""}
                    for i in invoices for kind in ("duplicate_invoice", "payment_allocation", "fx_rate_or_date", "reporting_period")][:30],
                "silence on faulty books": [],
                "correct findings submitted twice": findings + findings,
                "31 findings (over the limit)": (findings * 8)[:31],
            }
            for label, attack in attacks.items():
                e = JudgeEnv()
                e.reset(0, {"mode": "train", "episode_dir": str(episode)})
                reward = submit(e, m["episode_id"], attack)[1]
                print(f"   {label:<36} -> reward {reward:+.3f}")
            pause("contrast")


def env_tables_invoices(episode):
    from ledgergym.episode_io import load_public_episode
    return load_public_episode(episode / "public")["tables"]["invoices"]


if __name__ == "__main__":
    main()
