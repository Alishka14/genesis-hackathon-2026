"""LG-010: intentionally small *training-only* vertical-slice reference.

NOT a production financial generator, fault injector, or secure evaluator.
The private truth exists in the host Python process and is therefore NOT
isolated from untrusted Python code. Expose only JSON through a process boundary
before using it with an arbitrary AI agent.
"""
from __future__ import annotations

import ast
import json
import operator
import random
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_STEPS = 100
PUBLIC_TABLES = {"ledger", "invoices", "payments", "fx"}
TYPE_DUPLICATE = "duplicate_invoice"


def generate_fixture(seed: int, *, duplicate: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Generate a balanced tiny example and its evaluator-only ground truth."""
    rng = random.Random(seed)
    invoice_ids = [f"inv-{rng.getrandbits(48):012x}" for _ in range(2 if duplicate else 1)]
    doc_ids = [f"doc-{rng.getrandbits(48):012x}" for _ in invoice_ids]
    payment_id = f"pay-{rng.getrandbits(48):012x}"
    payment_doc_id = f"doc-{rng.getrandbits(48):012x}"
    amount = 125_000
    invoice_rows = [
        {
            "doc_id": doc_ids[i], "invoice_id": invoice_ids[i], "entity_id": "vendor-001",
            "issued_at": "2026-11-02T12:00:00+05:00",
            "due_at": "2026-11-30T23:59:00+05:00", "currency": "KZT",
            "total_minor": amount,
            "line_items": [{"purchase_order_id": "po-2026-17", "service_period": "2026-10", "amount_minor": amount}],
        }
        for i in range(len(invoice_ids))
    ]
    ledger = []
    row_num = 0

    def post(account: str, debit: int, credit: int, *, invoice_id: str | None = None, pid: str | None = None) -> None:
        nonlocal row_num
        row_num += 1
        ledger.append({
            "row_id": f"row-{row_num:04d}", "timestamp": "2026-11-02T12:00:00+05:00",
            "account": account, "debit_minor": debit, "credit_minor": credit,
            "currency": "KZT", "entity_id": "vendor-001", "invoice_id": invoice_id,
            "payment_id": pid,
        })

    for iid in invoice_ids:
        post("expense", amount, 0, invoice_id=iid)
        post("accounts_payable", 0, amount, invoice_id=iid)
    post("accounts_payable", amount, 0, pid=payment_id)
    post("cash", 0, amount, pid=payment_id)
    assert sum(x["debit_minor"] for x in ledger) == sum(x["credit_minor"] for x in ledger)

    payments = [{
        "doc_id": payment_doc_id, "payment_id": payment_id,
        "timestamp": "2026-11-04T12:00:00+05:00", "currency": "KZT",
        "amount_minor": amount, "invoice_refs": [invoice_ids[0]],
    }]
    public = {
        "manifest": {
            "schema_version": "integration-reference-0.1", "episode_id": f"ep-{seed:08d}",
            "base_currency": "KZT", "period_start": "2026-11-01T00:00:00+05:00",
            "period_end": "2026-11-30T23:59:59+05:00", "timezone": "+05:00",
            "currency_scale": {"KZT": 2},
            "counts": {"ledger": len(ledger), "documents": len(invoice_rows) + len(payments)},
            "rounding_policy": "ROUND_HALF_EVEN",
        },
        "policy": {
            "unique_obligation_basis": ["entity_id", "purchase_order_id", "service_period"],
            "fx_rate_date": "payment_timestamp", "rounding": "ROUND_HALF_EVEN",
            "cutoff": "period_end_inclusive",
        },
        "ledger": ledger, "invoices": invoice_rows, "payments": payments, "fx": [],
    }
    truth = ([{
        "issue_id": "private-issue-1", "type": TYPE_DUPLICATE,
        "affected_ids": sorted(invoice_ids), "expected_amount_minor": amount,
        "currency": "KZT", "allowed_evidence_sets": [doc_ids],
    }] if duplicate else [])
    return public, truth


def _calculate(expression: str) -> str:
    """Decimal arithmetic only; no names, attributes, calls, indexing, or eval."""
    if not isinstance(expression, str) or len(expression) > 120:
        raise ValueError("invalid_expression")
    tree = ast.parse(expression, mode="eval")
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def visit(node: ast.AST, depth: int = 0) -> Decimal:
        if depth > 20:
            raise ValueError("too_deep")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(expression, node)
            if not literal or len(literal) > 40:
                raise ValueError("invalid_number")
            try:
                return Decimal(literal)
            except InvalidOperation as exc:
                raise ValueError("invalid_number") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            result = visit(node.operand, depth + 1)
            return result if isinstance(node.op, ast.UAdd) else -result
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            try:
                value = binary[type(node.op)](left, right)
            except (ZeroDivisionError, InvalidOperation) as exc:
                raise ValueError("invalid_arithmetic") from exc
            if not value.is_finite() or abs(value) > Decimal("1e18"):
                raise ValueError("out_of_range")
            return value
        raise ValueError("forbidden_expression")

    value = visit(tree.body)
    if not value.is_finite() or abs(value) > Decimal("1e18"):
        raise ValueError("out_of_range")
    return format(value, "f")


def official_score(findings: list[dict[str, Any]], truth: list[dict[str, Any]], inspection_steps: int) -> dict[str, Any]:
    """Small transparent reference for the official reward, NOT production matcher."""
    if not isinstance(findings, list) or len(findings) > 30:
        return {"reward": -1, "error": "malformed_submit"}
    for finding in findings:
        if not isinstance(finding, dict):
            return {"reward": -1, "error": "malformed_submit"}
        required = {"type", "affected_ids", "claimed_amount_minor", "currency", "evidence_ids", "explanation"}
        if not required.issubset(finding):
            return {"reward": -1, "error": "malformed_submit"}
        if (not isinstance(finding["affected_ids"], list) or not isinstance(finding["evidence_ids"], list)
            or len(finding["evidence_ids"]) > 10 or not isinstance(finding["explanation"], str)
            or len(finding["explanation"]) > 1000 or type(finding["claimed_amount_minor"]) is not int
            or not isinstance(finding["type"], str) or not isinstance(finding["currency"], str)
            or any(not isinstance(x, str) for x in finding["affected_ids"] + finding["evidence_ids"])):
            return {"reward": -1, "error": "malformed_submit"}

    def matches(f: dict[str, Any], t: dict[str, Any]) -> bool:
        return (
            f["type"] == t["type"] and sorted(f["affected_ids"]) == sorted(t["affected_ids"])
            and f["currency"] == t["currency"] and f["claimed_amount_minor"] == t["expected_amount_minor"]
            and any(set(allowed).issubset(set(f["evidence_ids"])) for allowed in t["allowed_evidence_sets"])
        )

    linked_to: dict[int, int] = {}

    def augment(fi: int, seen: set[int]) -> bool:
        for ti, t in enumerate(truth):
            if ti in seen or not matches(findings[fi], t):
                continue
            seen.add(ti)
            if ti not in linked_to or augment(linked_to[ti], seen):
                linked_to[ti] = fi
                return True
        return False

    tp = sum(augment(fi, set()) for fi in range(len(findings)))
    fp, fn = len(findings) - tp, len(truth) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (1.0 if not truth and not findings else 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    reward = max(-1.0, min(1.0, 2 * f1 - 1 - 0.002 * inspection_steps))
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": f1, "reward": reward}


class ReferenceEnvironment:
    """Read-only JSON action environment for *trusted smoke tests only*."""

    def __init__(self, *, duplicate: bool = True):
        self.duplicate = duplicate
        self._public: dict[str, Any] = {}
        self._truth: list[dict[str, Any]] = []  # NOT isolated from Python code
        self.steps = 0
        self.done = False

    def reset(self, seed: int = 7, config: dict[str, Any] | None = None):
        if config and config.get("mode", "train") != "train":
            raise ValueError("reference_supports_train_only")
        self._public, self._truth = generate_fixture(seed, duplicate=self.duplicate)
        self.steps, self.done = 0, False
        observation = {"task": "Find evidence-backed financial discrepancies", "manifest": self._public["manifest"],
                       "policy_summary": self._public["policy"], "remaining_steps": MAX_STEPS}
        return observation, {"mode": "train", "schema_version": self._public["manifest"]["schema_version"]}

    def step(self, action: dict[str, Any]):
        if self.done:
            raise RuntimeError("episode_finished")
        self.steps += 1
        remaining = MAX_STEPS - self.steps
        name = action.get("type") if isinstance(action, dict) else None
        if name == "submit" and self.steps <= MAX_STEPS:
            self.done = True
            if action.get("episode_id", self._public["manifest"]["episode_id"]) != self._public["manifest"]["episode_id"]:
                result = {"reward": -1, "error": "malformed_submit"}
            else:
                result = official_score(action.get("findings"), self._truth, self.steps - 1)
            return {"status": "submitted", "remaining_steps": remaining}, result["reward"], True, False, result
        if self.steps >= MAX_STEPS:
            self.done = True
            return {"status": "budget_exhausted", "remaining_steps": 0}, 0.0, False, True, {"findings": []}

        out: dict[str, Any]
        if name == "list_records" and action.get("table") in PUBLIC_TABLES:
            table = action["table"]
            limit = action.get("limit", 50)
            cursor = action.get("cursor")
            try:
                start = int(cursor) if cursor is not None else 0
                if type(limit) is not int or not 1 <= limit <= 50 or start < 0 or str(start) != str(cursor) and cursor is not None:
                    raise ValueError
                rows = self._public[table]
                out = {"records": rows[start:start + limit], "next_cursor": str(start + limit) if start + limit < len(rows) else None}
            except (ValueError, TypeError):
                out = {"error": "invalid_pagination"}
        elif name == "get_record" and action.get("table") in PUBLIC_TABLES:
            row_id = action.get("id")
            rows = self._public[action["table"]]
            matches = [r for r in rows if row_id in [r.get("row_id"), r.get("invoice_id"), r.get("payment_id")]]
            out = {"record": matches[0]} if matches else {"error": "unknown_id"}
        elif name == "get_document":
            doc_id = action.get("doc_id")
            records = self._public["invoices"] + self._public["payments"]
            matches = [r for r in records if r.get("doc_id") == doc_id]
            out = {"document": matches[0]} if matches else {"error": "unknown_id"}
        elif name == "calculator":
            try:
                out = {"result": _calculate(action.get("expression"))}
            except (ValueError, SyntaxError, TypeError, ArithmeticError):
                out = {"error": "invalid_expression"}
        else:
            out = {"error": "unknown_action"}
        return {**out, "remaining_steps": remaining}, 0.0, False, False, {}


def demo(seed: int = 7) -> dict[str, Any]:
    env = ReferenceEnvironment(duplicate=True)
    obs, _ = env.reset(seed, config={"mode": "train"})
    listed, _, _, _, _ = env.step({"type": "list_records", "table": "invoices", "limit": 20, "cursor": None})
    invoices = listed["records"]
    for invoice in invoices:
        env.step({"type": "get_document", "doc_id": invoice["doc_id"]})
    findings = [{
        "type": TYPE_DUPLICATE, "affected_ids": sorted(i["invoice_id"] for i in invoices),
        "claimed_amount_minor": invoices[0]["total_minor"], "currency": "KZT",
        "evidence_ids": [i["doc_id"] for i in invoices],
        "explanation": "Same vendor, purchase order and service period billed twice.",
    }]
    _, reward, terminated, truncated, result = env.step({"type": "submit", "episode_id": obs["manifest"]["episode_id"], "findings": findings})
    return {"episode_id": obs["manifest"]["episode_id"], "reward": reward,
            "terminated": terminated, "truncated": truncated, "score": result,
            "inspection_steps": env.steps - 1}


if __name__ == "__main__":
    print(json.dumps(demo(), ensure_ascii=False, sort_keys=True, indent=2))
