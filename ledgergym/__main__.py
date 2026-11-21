"""Run a small, trusted local demonstration; no network or external data."""
import json
from .env import LedgerSandbox


def main():
    env = LedgerSandbox()
    initial, _ = env.reset(seed=42, config={'scenario': 'duplicate_invoice', 'fault': True})
    invoices = env.step({"action": "list_records", "table": "invoices", "limit": 50})[0]["records"]
    ledger = env.step({"action": "list_records", "table": "ledger", "limit": 50})[0]["records"]
    findings = []
    a, b = invoices
    if (a["entity_id"], a["currency"], a["line_items"]) == (b["entity_id"], b["currency"], b["line_items"]):
        expense_rows = [r["row_id"] for r in ledger if r["account"] == "expense" and r["invoice_id"] in (a["invoice_id"], b["invoice_id"])]
        findings.append({"type": "duplicate_invoice", "affected_ids": [a["invoice_id"], b["invoice_id"]], "claimed_amount_minor": b["total_minor"], "currency": b["currency"], "evidence_ids": [a["doc_id"], b["doc_id"], *expense_rows], "explanation": "Two invoice documents describe the same synthetic service and each has an expense posting."})
    _, reward, terminated, truncated, info = env.step({"action": "submit", "episode_id": initial["manifest"]["episode_id"], "findings": findings})
    print(json.dumps({"prototype": True, "scenario": "synthetic duplicate", "terminated": terminated, "truncated": truncated, "reward": reward, "score": info["score"]}, sort_keys=True))


if __name__ == "__main__":
    main()
