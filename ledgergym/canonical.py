"""Trusted judge transport. Only JSON messages cross the policy process boundary."""
import copy
from collections import Counter
import csv
import hashlib
import json
import logging
import math
from pathlib import Path
import time

from . import score
from .env import LedgerSandbox, _record_identifier
from .episode_io import load_public_episode
from .generator import generate_episode

LOG = logging.getLogger("ledgergym.judge")
METRICS = ("tp", "fp", "fn", "precision", "recall", "f1")
MAX_ACTION_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 10000
PUBLIC_FILES = ("manifest.json", "policy.json", "ledger.csv", "fx.csv", "payments.jsonl", "invoices.jsonl")
ERRORS = {"invalid_action": "Invalid action.", "invalid_submit": "Invalid findings structure.",
          "budget": "Action limit reached.", "timeout": "Episode deadline reached.",
          "protocol_error": "Invalid policy message."}
PRIVATE_FIELDS = {"seed", "truth", "provenance", "issues", "issue_id", "expected_amount_minor",
                  "allowed_evidence_sets"}


def bounded_json(value):
    """Bound direct Python inputs before formatting, copying or walking large graphs."""
    todo = [(value, 0)]
    nodes = chars = 0
    while todo:
        item, depth = todo.pop()
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            return False
        kind = type(item)
        if kind is str:
            chars += len(item)
        elif kind in (dict, list):
            if len(item) + nodes + len(todo) > MAX_NODES:
                return False
            if kind is dict:
                for key in item:
                    if type(key) is not str:
                        return False
                    chars += len(key)
                children = item.values()
            else:
                children = item
            todo.extend((child, depth + 1) for child in children)
        elif kind is int:
            if item.bit_length() > 4096:
                return False
        elif kind is float:
            if not math.isfinite(item):
                return False
        elif item is not None and kind is not bool:
            return False
        if chars > MAX_ACTION_BYTES:
            return False
    return True


def _validate_public(public):
    if not isinstance(public["manifest"]["episode_id"], str) or not isinstance(public["policy"], dict):
        raise ValueError()
    for table, rows in public["tables"].items():
        for row in rows:
            if not isinstance(row, dict) or not isinstance(_record_identifier(table, row), str):
                raise ValueError()
            if table in ("invoices", "payments") and not isinstance(row.get("doc_id"), str):
                raise ValueError()
    pending = [public]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if PRIVATE_FIELDS.intersection(value):
                raise ValueError()
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    json.dumps(public, allow_nan=False)


def _load_parts(root):
    folder = Path(root) / "public"
    resolved = Path(root).resolve() / "public"
    if folder.resolve() != resolved or any((folder / name).resolve() != resolved / name for name in PUBLIC_FILES):
        raise ValueError()
    public = load_public_episode(folder)
    _validate_public(public)
    truth = json.loads((Path(root) / "private" / "truth.json").read_text(encoding="utf-8"))
    if not isinstance(truth["issues"], list):
        raise ValueError()
    for issue in truth["issues"]:
        if (not isinstance(issue, dict) or not isinstance(issue["type"], str)
                or not isinstance(issue["currency"], str) or type(issue["expected_amount_minor"]) is not int
                or not isinstance(issue["affected_ids"], list)
                or not all(isinstance(x, str) for x in issue["affected_ids"])
                or not isinstance(issue["allowed_evidence_sets"], list)
                or not all(isinstance(group, list) and all(isinstance(x, str) for x in group)
                           for group in issue["allowed_evidence_sets"])):
            raise ValueError()
    return public, truth


def _scorer(public, truth):
    ids = set()
    for table, rows in public["tables"].items():
        counts = Counter(_record_identifier(table, row) for row in rows)
        ids.update(key for key, count in counts.items() if count == 1)
        if table in ("invoices", "payments"):
            ids.update(row["doc_id"] for row in rows)
    def evaluate(findings, steps):
        return score.evaluate(truth["issues"], findings, ids, steps)
    return evaluate


def invalid_score():
    LOG.warning("Invalid findings structure")
    return {**dict.fromkeys(METRICS), "return": -1.0}


def _metrics(result):
    return {**{key: result[key] for key in METRICS}, "return": result["reward"]}


def score_episode(episode_dir, findings, inspection_steps):
    if type(inspection_steps) is not int or not 0 <= inspection_steps <= 100:
        raise ValueError("invalid inspection count")
    try:
        public, truth = _load_parts(episode_dir)
    except (OSError, ValueError, TypeError, KeyError, csv.Error, RecursionError, OverflowError):
        raise ValueError("invalid episode") from None
    if not bounded_json(findings) or not score.validate_submission(findings, public["manifest"]["episode_id"]):
        return invalid_score()
    return _metrics(_scorer(public, truth)(findings["findings"], inspection_steps))


def _transport(action):
    """Convert the published envelope. Invalid submits remain terminal submissions."""
    if type(action) is not dict:
        return {}
    name = action.get("name")
    malformed = {"action": "submit"} if name == "submit" else {}
    if (not bounded_json(action) or set(action) != {"name", "args"}
            or type(action["args"]) is not dict or type(name) is not str):
        return malformed
    args = action["args"]
    if name == "submit":
        if set(args) != {"findings"} or type(args["findings"]) is not dict:
            return malformed
        envelope = args["findings"]
        if set(envelope) != {"episode_id", "findings"}:
            return malformed
        return {"action": "submit", **envelope}
    if "action" in args:
        return {}
    return {"action": name, **args}


class JudgeEnv:
    def __init__(self, *, timeout=60):
        if type(timeout) not in (float, int) or not 0 < timeout <= 60:
            raise ValueError("invalid timeout")
        self.timeout = timeout
        self._native = None
        self._score = None
        self.deadline = None

    @property
    def final_score(self):
        """Evaluator-only frozen metrics; never included in a policy message."""
        return copy.deepcopy(self._score)

    def reset(self, seed, config):
        start = time.monotonic()
        self.deadline = start + self.timeout
        self._native = None
        self._score = None
        try:
            mode = config["mode"]
            if mode not in ("closed", "train") or type(seed) is not int:
                raise ValueError()
            if "episode_dir" in config:
                public, truth = _load_parts(config["episode_dir"])
            elif mode == "train":
                public, truth = generate_episode(seed, config["team_config"])
            else:
                raise ValueError()
            identity = public["manifest"]["episode_id"]
            def cursor(table, offset):
                encoded = json.dumps([identity, table, offset], separators=(",", ":")).encode("utf-8")
                return hashlib.sha256(encoded).hexdigest()
            evaluate = _scorer(public, truth)
            def freeze(findings, steps):
                result = evaluate(findings, steps)
                self._score = _metrics(result)
                return result
            native = LedgerSandbox(public, freeze, closed=mode == "closed",
                                   timeout=self.timeout, cursor_factory=cursor)
            obs, info = native.reset()
            native.started = start
            obs["task"] = "Inspect the accounting records and submit evidence for any discrepancies."
            self._native = native
            return obs, info
        except (OSError, ValueError, TypeError, KeyError, csv.Error, RecursionError, OverflowError):
            raise ValueError("invalid episode") from None

    def _response(self, result, error, reward, terminated, truncated):
        obs = {"result": result, "error": {"code": error, "message": ERRORS[error]} if error else None,
               "remaining_steps": 100 - self._native.steps}
        return obs, reward, terminated, truncated, {}

    def abort(self, reason):
        """Supervisor-only endpoint. Freeze empty findings without charging an action."""
        if self._native is None or self._native.done:
            raise RuntimeError("episode inactive")
        _, reward, _, _, _ = self._native._finish([], truncated=True)
        return self._response(None, reason, reward, False, True)

    def step(self, action):
        native = self._native
        if native is None or native.done:
            raise RuntimeError("episode inactive")
        if time.monotonic() >= self.deadline:
            return self.abort("timeout")
        flat = _transport(action)
        obs, reward, terminated, truncated, _ = native.step(flat)
        if time.monotonic() >= self.deadline:
            # Expiry during decoding, a read or scoring wins over acceptance.
            inspections = native.steps - int(terminated and flat.get("action") == "submit")
            _, reward, _, _, _ = native._finish([], truncated=True, inspection_steps=inspections)
            return self._response(None, "timeout", reward, False, True)
        code = None
        result = None
        if truncated:
            code = "budget"
        elif obs.get("status") == "invalid_submit":
            self._score = invalid_score()
            code = "invalid_submit"
        elif terminated:
            result = {"accepted": True}
        elif "error" in obs:
            code = "invalid_action"
        elif flat["action"] == "list_records":
            result = {"records": obs["records"], "next_cursor": obs["next_cursor"]}
        else:
            key = {"get_document": "document", "get_record": "record", "calculator": "value"}[flat["action"]]
            result = obs[key]
        return self._response(result, code, reward, terminated, truncated)
