"""FinTech case section 10, done the way the jury describes it.

* Reproducibility: permuting rows and bijectively renaming every ID preserves
  the oracle answer and reward (with the new IDs), through JudgeEnv and
  score_episode, for ID formats unlike ours.
* Data: reverting the interventions recorded in provenance.json restores
  balanced books; every truth evidence set is reachable through the tools.
"""
import copy
import csv
import io
import json
import random
import re
import shutil
from collections import defaultdict

import pytest

import judge_adapter
from ledgergym.canonical import JudgeEnv
from ledgergym.episode_io import load_public_episode

ID = re.compile(r"^(id|episode|private)-[0-9a-f]{32}$")
KEYS = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id", "fx": "rate_id"}
CONFIGS = [
    {"scenario": "company", "faults": {"duplicate_invoice": 1, "payment_allocation": 1,
                                       "fx_rate_or_date": 1, "reporting_period": 1},
     "compounds": {"fx_allocation": 1, "duplicate_allocation": 1}},
    {"scenario": "company", "faults": {"fx_rate_or_date": 2, "duplicate_invoice": 1},
     "fault_parameters": "varied", "timestamp_offsets": "mixed", "evidence_alternatives": True},
    {"scenario": "company"},
]
STYLES = [lambda n: f"INV/2026/{n:06d}", lambda n: f"r{n}", lambda n: f"Ω-{n}-ζ"]


def _oracle(truth, episode_id):
    return {"episode_id": episode_id, "findings": [
        {"type": i["type"], "affected_ids": list(i["affected_ids"]),
         "claimed_amount_minor": i["expected_amount_minor"], "currency": i["currency"],
         "evidence_ids": list(i["allowed_evidence_sets"][0]), "explanation": "oracle"}
        for i in truth["issues"]]}


def _run(episode):
    truth = json.loads((episode / "private" / "truth.json").read_text())
    manifest = json.loads((episode / "public" / "manifest.json").read_text())
    submission = _oracle(truth, manifest["episode_id"])
    env = JudgeEnv()
    env.reset(0, {"mode": "closed", "episode_dir": str(episode)})
    env.step({"name": "list_records", "args": {"table": "ledger", "limit": 5}})
    env.step({"name": "submit", "args": {"findings": submission}})
    return env.final_score, judge_adapter.score_episode(episode, submission, 1)


def _transform(src, dst, rng, make):
    mapping = {}

    def m(value):
        if isinstance(value, str) and ID.match(value):
            return mapping.setdefault(value, make(len(mapping) + 1))
        if isinstance(value, list):
            return [m(x) for x in value]
        if isinstance(value, dict):
            return {k: m(x) for k, x in value.items()}
        return value
    shutil.copytree(src, dst)
    for path in (dst / "public").iterdir():
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            path.write_text(json.dumps(m(json.loads(text))), encoding="utf-8")
        elif path.suffix == ".jsonl":
            rows = [m(json.loads(line)) for line in text.splitlines() if line.strip()]
            rng.shuffle(rows)
            path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        elif path.suffix == ".csv":
            head, *body = list(csv.reader(io.StringIO(text)))
            body = [[m(cell) for cell in row] for row in body]
            rng.shuffle(body)
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(head)
            writer.writerows(body)
            path.write_text(out.getvalue(), encoding="utf-8")
    truth = dst / "private" / "truth.json"
    truth.write_text(json.dumps(m(json.loads(truth.read_text()))), encoding="utf-8")
    return mapping


@pytest.mark.parametrize("config_index", range(len(CONFIGS)))
def test_permutation_and_id_renaming_preserve_oracle_reward(tmp_path, config_index):
    base = tmp_path / "base"
    judge_adapter.generate_episode(40 + config_index, CONFIGS[config_index], base)
    reference = _run(base)
    assert reference[0]["f1"] == 1
    for index, make in enumerate(STYLES):
        variant = tmp_path / f"variant-{index}"
        mapping = _transform(base, variant, random.Random(index), make)
        assert mapping and all(not ID.match(v) for v in mapping.values())
        assert _run(variant) == reference


def _equalities(tables):
    totals = defaultdict(lambda: [0, 0])
    for row in tables["ledger"]:
        totals[row["currency"]][0] += row["debit_minor"]
        totals[row["currency"]][1] += row["credit_minor"]
    problems = [currency for currency, (debit, credit) in totals.items() if debit != credit]
    problems += [i["invoice_id"] for i in tables["invoices"]
                 if i["total_minor"] != sum(line["amount_minor"] for line in i["line_items"])]
    problems += [p["payment_id"] for p in tables["payments"]
                 if p["amount_minor"] != sum(ref["amount_minor"] for ref in p["invoice_refs"])]
    return problems


@pytest.mark.parametrize("seed", [201, 202, 203])
@pytest.mark.parametrize("config_index", [0, 1])
def test_books_balance_before_interventions_and_evidence_is_reachable(tmp_path, seed, config_index):
    episode = tmp_path / "ep"
    judge_adapter.generate_episode(seed, CONFIGS[config_index], episode)
    public = load_public_episode(episode / "public")
    provenance = json.loads((episode / "private" / "provenance.json").read_text())
    truth = json.loads((episode / "private" / "truth.json").read_text())
    assert truth["issues"] and provenance["interventions"]

    tables = copy.deepcopy(public["tables"])
    index = {}
    for name, rows in tables.items():
        for row in rows:
            index[(name, row.get(KEYS[name]))] = row
            for line in row.get("line_items", []) if name == "invoices" else []:
                index[("invoices.line_items", line["line_id"])] = line
    for change in reversed(provenance["interventions"]):
        record = index[(change["table"], change["id"])]
        assert record[change["field"]] == change["after"]
        record[change["field"]] = change["before"]
    assert _equalities(tables) == []

    reachable = {row.get(KEYS[name]) for name, rows in public["tables"].items() for row in rows}
    reachable |= {row["doc_id"] for name in ("invoices", "payments") for row in public["tables"][name]}
    for issue in truth["issues"]:
        assert set(issue["affected_ids"]) <= reachable
        assert any(set(group) <= reachable for group in issue["allowed_evidence_sets"])
