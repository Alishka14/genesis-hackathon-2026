"""Opt-in generator variation (fault_parameters / timestamp_offsets / evidence_alternatives).

Covers: legacy byte-identity, input validation, real diversity across seeds, unchanged
instants under mixed offsets, independent agreement, alternative evidence in the judge.
"""
import copy
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from ledgergym.company_checks import validate_company
from ledgergym.company_world import OPTIONS, build_company
from ledgergym.independent_audit import audit_company_public
from ledgergym.score import accessible_evidence_ids, evaluate
import judge_adapter

VARIED = {"fault_parameters": "varied", "timestamp_offsets": "mixed", "evidence_alternatives": True}
MIX = {"faults": {"fx_rate_or_date": 2, "duplicate_invoice": 2, "payment_allocation": 2, "reporting_period": 2},
       "compounds": {"fx_allocation": 1, "duplicate_allocation": 1}}
ZONE = timezone(timedelta(hours=5))


def _digest(world):
    return hashlib.sha256(json.dumps(world, sort_keys=True).encode()).hexdigest()[:16]


@pytest.mark.parametrize("seed,config,digest", [
    (0, {}, "ff4f8a50475508c4"),
    (7, {}, "3a05fe70b291dd9a"),
    (0, MIX, "3764a87714302d0e"),
    (7, MIX, "084ce22e3fccbee7"),
])
def test_legacy_configs_are_byte_identical_to_main_5086632(seed, config, digest):
    # Digests of (public, truth, provenance) recorded from main 508663205dd0 before this change.
    assert _digest(build_company(seed, config)) == digest


def test_explicit_defaults_equal_omitted_options_except_recorded_config():
    explicit = {key: default for key, (default, _) in OPTIONS.items()}
    public, truth, provenance = build_company(3, {**MIX, **explicit})
    legacy = build_company(3, MIX)
    assert (public, truth) == legacy[:2]
    assert not set(legacy[2]["config"]) & set(OPTIONS)
    assert all(key in provenance["config"] for key in OPTIONS)


@pytest.mark.parametrize("key,value", [
    ("fault_parameters", "random"), ("fault_parameters", 1), ("timestamp_offsets", "Mixed"),
    ("evidence_alternatives", 1), ("evidence_alternatives", "yes"), ("variation", "varied"),
])
def test_invalid_option_values_are_rejected(key, value):
    with pytest.raises(ValueError):
        build_company(0, {key: value})


def _local(stamp):
    return datetime.fromisoformat(stamp).astimezone(ZONE)


def _observed(seeds, options):
    shifts, fractions, dup_currencies, offsets = Counter(), Counter(), Counter(), Counter()
    for seed in seeds:
        public, truth, _ = build_company(seed, {**MIX, **options})
        tables = public["tables"]
        payments = {p["payment_id"]: p for p in tables["payments"]}
        invoices = {i["invoice_id"]: i for i in tables["invoices"]}
        rates = {r["rate_id"]: r for r in tables["fx"]}
        ledger = {r["row_id"]: r for r in tables["ledger"]}
        offsets.update(datetime.fromisoformat(r["timestamp"]).utcoffset() for r in tables["ledger"])
        for issue in truth["issues"]:
            if issue["type"] == "fx_rate_or_date":
                pay = next(payments[x] for x in issue["affected_ids"] if x in payments)
                row = next(ledger[x] for x in issue["affected_ids"] if x in ledger)
                used = datetime.fromisoformat(rates[row["rate_id"]]["date"]).date()
                shifts[(used - _local(pay["timestamp"]).date()).days] += 1
            elif issue["type"] == "payment_allocation":
                pay = next(payments[x] for x in issue["affected_ids"] if x in payments)
                ref = pay["invoice_refs"][0]
                if ref["invoice_id"] == pay["remittance_invoice_id"]:
                    fractions[round(4 * ref["amount_minor"] / pay["amount_minor"])] += 1
            elif issue["type"] == "duplicate_invoice":
                dup_currencies[invoices[issue["affected_ids"][0]]["currency"]] += 1
    return shifts, fractions, dup_currencies, offsets


def test_fixed_mode_keeps_legacy_patterns():
    shifts, fractions, currencies, offsets = _observed(range(20), {})
    assert set(shifts) == {-1} and set(fractions) == {2} and set(currencies) == {"KZT"}
    assert len(offsets) <= 2


def test_varied_mode_really_varies_across_seeds():
    shifts, fractions, currencies, offsets = _observed(range(40), VARIED)
    assert {d for d in shifts if d < 0} and {d for d in shifts if d > 0} and len(shifts) >= 5
    assert set(fractions) == {1, 2, 3}
    assert set(currencies) == {"KZT", "USD"}
    assert len(offsets) == 5


def test_mixed_offsets_change_representation_not_instants():
    uniform = build_company(5, {**MIX, "fault_parameters": "varied"})
    mixed = build_company(5, {**MIX, "fault_parameters": "varied", "timestamp_offsets": "mixed"})
    assert uniform[1] == mixed[1]          # identical labels and amounts
    changed = 0
    for table in ("invoices", "payments", "ledger"):
        for a, b in zip(uniform[0]["tables"][table], mixed[0]["tables"][table]):
            for field in ("issued_at", "due_at", "timestamp"):
                if field in a:
                    assert datetime.fromisoformat(a[field]) == datetime.fromisoformat(b[field])
                    changed += a[field] != b[field]
            assert {k: v for k, v in a.items() if k not in ("issued_at", "due_at", "timestamp")} == \
                   {k: v for k, v in b.items() if k not in ("issued_at", "due_at", "timestamp")}
    assert changed > 0


@pytest.mark.parametrize("seed", range(12))
def test_varied_worlds_agree_with_independent_public_auditor(seed):
    for config in ({}, MIX):
        public, truth, _ = build_company(seed, {**config, **VARIED})
        expected = sorted((i["type"], tuple(sorted(i["affected_ids"])), i["expected_amount_minor"], i["currency"])
                          for i in truth["issues"])
        assert [tuple(x) for x in audit_company_public(public)["issues"]] == [tuple(x) for x in expected]


def _finding(issue, evidence):
    return {"type": issue["type"], "affected_ids": issue["affected_ids"],
            "claimed_amount_minor": issue["expected_amount_minor"], "currency": issue["currency"],
            "evidence_ids": evidence, "explanation": ""}


def test_alternative_evidence_sets_are_smaller_sufficient_subsets():
    public, truth, _ = build_company(2, {**MIX, "evidence_alternatives": True})
    invoice_docs = {i["doc_id"] for i in public["tables"]["invoices"]}
    for issue in truth["issues"]:
        sets = issue["allowed_evidence_sets"]
        if issue["type"] in ("fx_rate_or_date", "duplicate_invoice"):
            assert len(sets) == 2 and set(sets[1]) < set(sets[0])
            if issue["type"] == "fx_rate_or_date":
                assert set(sets[1]) == set(sets[0]) - invoice_docs
            else:
                assert set(sets[1]) == set(sets[0]) & invoice_docs and len(sets[1]) == 2
        else:
            assert len(sets) == 1


def test_judge_accepts_each_allowed_set_and_rejects_incomplete_ones():
    public, truth, _ = build_company(2, {**MIX, "evidence_alternatives": True})
    ids = accessible_evidence_ids(public)
    issues = [i for i in truth["issues"] if len(i["allowed_evidence_sets"]) == 2]
    assert issues
    for issue in issues:
        canonical, minimal = issue["allowed_evidence_sets"]
        for evidence in (canonical, minimal):
            assert evaluate([issue], [_finding(issue, evidence)], ids, 0)["tp"] == 1
        for missing in minimal:
            short = [x for x in minimal if x != missing]
            assert evaluate([issue], [_finding(issue, short)], ids, 0)["tp"] == 0


def test_minimal_set_is_not_accepted_when_option_is_off():
    public, truth, _ = build_company(2, MIX)
    alt_public, alt_truth, _ = build_company(2, {**MIX, "evidence_alternatives": True})
    assert public == alt_public
    ids = accessible_evidence_ids(public)
    for legacy, alt in zip(truth["issues"], alt_truth["issues"]):
        if len(alt["allowed_evidence_sets"]) == 2:
            assert evaluate([legacy], [_finding(legacy, alt["allowed_evidence_sets"][1])], ids, 0)["tp"] == 0


def test_validator_requires_canonical_chain_and_sufficient_subsets():
    public, truth, _ = build_company(2, {**MIX, "evidence_alternatives": True})
    validate_company(public, truth)
    issue_index = next(k for k, i in enumerate(truth["issues"]) if len(i["allowed_evidence_sets"]) == 2)
    only_minimal = copy.deepcopy(truth)
    only_minimal["issues"][issue_index]["allowed_evidence_sets"] = [truth["issues"][issue_index]["allowed_evidence_sets"][1]]
    with pytest.raises(ValueError, match="canonical evidence chain missing"):
        validate_company(public, only_minimal)
    too_small = copy.deepcopy(truth)
    too_small["issues"][issue_index]["allowed_evidence_sets"][1] = truth["issues"][issue_index]["allowed_evidence_sets"][1][:-1]
    with pytest.raises(ValueError, match="unsupported evidence"):
        validate_company(public, too_small)


def test_judge_train_reset_accepts_variation_options():
    env = judge_adapter.make_env()
    obs, info = env.reset(4, {"mode": "train", "team_config": {"scenario": "company", **MIX, **VARIED}})
    assert obs["manifest"]["schema_version"] == "0.3-company" and info == {}


def test_varied_dataset_keeps_public_index_schema_and_records_options_privately(tmp_path):
    from ledgergym.company_dataset import VARIED_OPTIONS, create_company_dataset
    index = create_company_dataset(tmp_path / "varied", varied=True)
    assert set(index) == {"kind", "train", "dev"}
    recorded = 0
    for split in ("train", "dev"):
        for entry in index[split]:
            provenance = json.loads((tmp_path / "varied" / entry["path"] / "private" / "provenance.json").read_text())
            assert all(provenance["config"].get(k) == v for k, v in VARIED_OPTIONS.items())
            recorded += 1
            public_text = "".join(p.read_text() for p in (tmp_path / "varied" / entry["path"] / "public").iterdir())
            assert not any(k in public_text for k in VARIED_OPTIONS)
    assert recorded == 20
    with pytest.raises(ValueError):
        create_company_dataset(tmp_path / "bad", varied="yes")
