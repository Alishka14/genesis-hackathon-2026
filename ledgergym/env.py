"""Development environment. In-process callbacks are NOT a security boundary."""
import ast
import copy
from decimal import Decimal, DecimalException, localcontext
import operator
import re
import time
from .score import validate_submission


def calculate(expression):
    if not isinstance(expression, str) or len(expression) > 128:
        raise ValueError("invalid expression")
    tree = ast.parse(expression, mode="eval")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    if sum(1 for _ in ast.walk(tree)) > 50:
        raise ValueError("too complex")
    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(expression, node)
            if not literal or not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", literal):
                raise ValueError("invalid number")
            value = Decimal(literal)
            if abs(value) > Decimal("1e18"):
                raise ValueError("out of range")
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = walk(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            value = ops[type(node.op)](walk(node.left), walk(node.right))
            if not value.is_finite() or abs(value) > Decimal('1e30'):
                raise ValueError("out of range")
            return value
        raise ValueError("unsupported expression")
    with localcontext() as ctx:
        ctx.prec = 28
        return str(walk(tree.body))


class LedgerSandbox:
    def __init__(self, public, evaluator, closed=False, timeout=60):
        self.public = copy.deepcopy(public)
        self.evaluator = evaluator
        self.closed = closed
        self.timeout = timeout
        self.done = True

    def reset(self, seed=None, config=None):
        self.steps = 0
        self.started = time.monotonic()
        self.done = False
        return {"manifest": copy.deepcopy(self.public["manifest"]), "policy": copy.deepcopy(self.public["policy"]), "remaining_steps": 100}, {}

    def step(self, action):
        if self.done:
            raise RuntimeError("episode ended; reset required")
        if time.monotonic() - self.started >= self.timeout:
            return self._finish([], truncated=True)
        self.steps += 1
        kind = action.get("action") if isinstance(action, dict) else None
        if kind == "submit":
            submission = {"episode_id": action.get("episode_id"), "findings": action.get("findings")}
            if set(action) != {"action", "episode_id", "findings"} or not validate_submission(submission, self.public["manifest"]["episode_id"]):
                self.done = True
                return {"status": "invalid_submit", "remaining_steps": 100 - self.steps}, 0.0 if self.closed else -1.0, True, False, {}
            return self._finish(submission["findings"])
        if self.steps >= 100:
            return self._finish([], truncated=True)
        try:
            obs = self._read(action, kind)
        except (ValueError, TypeError, KeyError, SyntaxError, DecimalException, ZeroDivisionError, OverflowError, RecursionError):
            obs = {"error": "invalid_action"}
        obs["remaining_steps"] = 100 - self.steps
        return copy.deepcopy(obs), 0.0, False, False, {}

    def _read(self, action, kind):
        tables = self.public["tables"]
        if kind == "list_records":
            table, cursor, limit = action.get("table"), action.get("cursor"), action.get("limit", 50)
            if not isinstance(table, str) or table not in tables or type(limit) is not int or not 1 <= limit <= 50:
                raise ValueError()
            offset = 0
            if cursor is not None:
                prefix = self.public["manifest"]["episode_id"] + ":" + table + ":"
                if not isinstance(cursor, str) or not cursor.startswith(prefix) or not cursor[len(prefix):].isascii() or not cursor[len(prefix):].isdigit():
                    raise ValueError()
                offset = int(cursor[len(prefix):])
            if offset > len(tables[table]):
                raise ValueError()
            rows = tables[table][offset:offset + limit]
            next_offset = offset + len(rows)
            next_cursor = f'{self.public["manifest"]["episode_id"]}:{table}:{next_offset}' if next_offset < len(tables[table]) else None
            return {"records": rows, "next_cursor": next_cursor}
        if kind == "get_record":
            table, record_id = action.get("table"), action.get("id")
            if not isinstance(table, str) or table not in tables or not isinstance(record_id, str):
                raise ValueError()
            key = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id"}.get(table)
            for row in tables[table]:
                if key and row.get(key) == record_id:
                    return {"record": row}
            raise ValueError()
        if kind == "get_document":
            doc_id = action.get("doc_id")
            if not isinstance(doc_id, str):
                raise ValueError()
            for table in ("invoices", "payments"):
                for row in tables[table]:
                    if row.get("doc_id") == doc_id:
                        return {"document": row}
            raise ValueError()
        if kind == "calculator":
            return {"value": calculate(action.get("expression"))}
        raise ValueError()

    def _finish(self, findings, truncated=False):
        self.done = True
        score = self.evaluator(findings, self.steps if truncated else self.steps - 1)
        if self.closed:
            return {"status": "finished", "remaining_steps": max(0, 100 - self.steps)}, 0.0, not truncated, truncated, {}
        return {"status": "finished", "remaining_steps": max(0, 100 - self.steps)}, score["reward"], not truncated, truncated, {"score": score}
