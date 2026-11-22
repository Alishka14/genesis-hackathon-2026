"""Independent regression checks for opt-in period and FX-shape generalization.

These cases deliberately use held-out months, leap years, year boundaries,
nonmonotonic FX prices, multiple interacting faults and the real judge API.
Default February 2026 fixtures and their fixed hashes remain unchanged.
"""
from calendar import monthrange
from datetime import date, timedelta, datetime
import json

import pytest

import judge_adapter
from ledgergym.company_world import build_company
from ledgergym.company_checks import inspect_company
from ledgergym.independent_audit import audit_company_public


STRESS = {
    "postings": 2000,
    "documents": 200,
    "faults": {
        "duplicate_invoice": 2,
        "payment_allocation": 2,
        "fx_rate_or_date": 2,
        "reporting_period": 2,
    },
    "compounds": {"fx_allocation": 1, "duplicate_allocation": 1},
}
OPTIONS = {
    "fx_rate_pattern": "volatile",
    "fault_parameters": "varied",
    "timestamp_offsets": "mixed",
    "evidence_alternatives": True,
}
MONTHS = ("2020-02", "2025-01", "2026-02", "2027-04",
          "2028-02", "2030-12", "2039-12")


def signature(issue):
    return (issue["type"], tuple(sorted(issue["affected_ids"])),
            issue["expected_amount_minor"], issue["currency"])


@pytest.mark.parametrize("month", MONTHS)
@pytest.mark.parametrize("seed", (0, 17))
def test_held_out_month_fx_and_twelve_faults_match_public_audit(month, seed):
    public, truth, provenance = build_company(
        seed, {**STRESS, **OPTIONS, "reporting_month": month})
    manifest, tables = public["manifest"], public["tables"]
    year, number = map(int, month.split("-"))
    assert manifest["period_start"] == f"{month}-01T00:00:00+05:00"
    assert manifest["period_end"] == (
        f"{month}-{monthrange(year, number)[1]:02d}T23:59:59+05:00")
    assert len(truth["issues"]) == 12
    assert len(tables["ledger"]) == 2000
    assert provenance["config"]["reporting_month"] == month

    # ISO offsets can vary but every posting belongs to the chosen local month.
    for row in tables["ledger"]:
        assert datetime.fromisoformat(row["timestamp"]).astimezone(
            datetime.fromisoformat(manifest["period_start"]).tzinfo
        ).strftime("%Y-%m") == month

    audited = audit_company_public(public)
    assert audited["issues"] == sorted(map(signature, truth["issues"]))
    assert len(inspect_company(public)) == len(truth["issues"])
    assert all(issue["expected_amount_minor"] > 0
               for issue in truth["issues"]
               if issue["type"] == "fx_rate_or_date")

    days = {row["date"]: row["rate"] for row in tables["fx"]}
    assert len(days) == len(set(days.values())) == 29
    previous = (date(year, number, 1) - timedelta(days=1)).isoformat()
    assert previous in days


@pytest.mark.parametrize("key,value", [
    ("reporting_month", "2019-12"), ("reporting_month", "2040-01"),
    ("reporting_month", "2028-2"), ("reporting_month", "2027-13"),
    ("reporting_month", None), ("fx_rate_pattern", "constant"),
    ("fx_rate_pattern", None), ("fx_rate_pattern", True),
])
def test_new_variation_options_are_strictly_validated(key, value):
    with pytest.raises(ValueError):
        build_company(1, {key: value})


def test_volatile_fx_quotes_are_nonmonotonic_and_deterministic():
    seen = []
    for seed in range(8):
        config = {**OPTIONS, "reporting_month": "2028-02"}
        p, t, x = build_company(seed, config)
        assert (p, t, x) == build_company(seed, config)
        values = [int(round(float(r["rate"]) * 100))
                  for r in sorted(p["tables"]["fx"], key=lambda r: r["date"])]
        seen.extend(b - a for a, b in zip(values, values[1:]))
    assert any(x < 0 for x in seen)
    assert any(x > 0 for x in seen)
    assert len(set(seen)) > 12


def test_new_month_can_be_exported_and_scored_by_closed_judge(tmp_path):
    episode = tmp_path / "episode"
    config = {
        "scenario": "company", "reporting_month": "2030-12",
        "fx_rate_pattern": "volatile",
        "fault_parameters": "varied",
        "faults": {"fx_rate_or_date": 1, "reporting_period": 1},
        "compounds": {"fx_allocation": 1},
    }
    judge_adapter.generate_episode(37, config, episode)
    env = judge_adapter.make_env()
    obs, info = env.reset(37, {"mode": "closed", "episode_dir": str(episode)})
    assert info == {}
    assert obs["manifest"]["period_start"].startswith("2030-12-01")
    truth = json.loads((episode / "private" / "truth.json").read_text())
    findings = [
        {"type": i["type"], "affected_ids": i["affected_ids"],
         "claimed_amount_minor": i["expected_amount_minor"],
         "currency": i["currency"], "evidence_ids": i["allowed_evidence_sets"][0],
         "explanation": ""}
        for i in truth["issues"]
    ]
    response, reward, terminated, truncated, extra = env.step({
        "name": "submit",
        "args": {"findings": {"episode_id": obs["manifest"]["episode_id"],
                              "findings": findings}},
    })
    assert reward == 0.0 and terminated and not truncated and extra == {}
    assert response["result"] == {"accepted": True}
    assert env.final_score["f1"] == 1.0
    assert env.final_score["return"] == 1.0
