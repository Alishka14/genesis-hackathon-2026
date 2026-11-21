"""Integration gate output contracts, independent of the running suite."""
import json

import pytest

from scripts import verify_integration as gate


POLICIES = ("seeded_random", "reconciliation", "mark_all", "oracle")


def mixed_summary():
    counts = {"accrual_company_v1": 8, "accrual_company_v2": 2}
    labels = {"clean": 1, "faulty": 1}
    return {
        "kind": "synthetic_company_development_with_settlements",
        "replay": {"trajectories": 60, "score_matches": 60},
        "model_counts": {"train": dict(counts), "dev": dict(counts)},
        "v2_label_counts": {"train": dict(labels), "dev": dict(labels)},
        "splits": {
            split: {policy: {"episodes": 10} for policy in POLICIES}
            for split in ("train", "dev")
        },
        "policies": {name: {"mean_f1": 1} for name in ("reconciliation", "oracle")},
        "clean_false_accusations": {
            "overall": {
                model: {"reconciliation": {"fp": 0}}
                for model in ("accrual_company_v1", "accrual_company_v2")
            }
        },
    }


def paired_summary():
    return {
        "kind": "internal_v2_causal_pairs_v1", "pairs": 6,
        "modes": {f"mode-{i}": {} for i in range(6)},
        "policies": {
            name: {"pairs": 6, "both_correct": 6, "fault_tp": 8,
                   "clean_fp": 0, "paired_accuracy": 1}
            for name in ("reconciliation", "oracle")
        },
    }


def test_mixed_gate_accepts_balanced_models_and_private_replay_counts():
    report = gate._assert_company_metrics(mixed_summary())
    assert report == {
        "episodes": 20, "replayed_trajectories": 60,
        "models_per_split": {"accrual_company_v1": 8, "accrual_company_v2": 2},
        "v2_labels_per_split": {"clean": 1, "faulty": 1},
    }


@pytest.mark.parametrize("change", [
    ("replay", "score_matches", 59),
    ("v2_label_counts", "train", {"clean": 2, "faulty": 0}),
    ("model_counts", "dev", {"accrual_company_v1": 10, "accrual_company_v2": 0}),
])
def test_mixed_gate_rejects_hidden_integration_regressions(change):
    target, key, value = change
    report = mixed_summary()
    report[target][key] = value
    with pytest.raises(ValueError):
        gate._assert_company_metrics(report)


def test_mixed_gate_rejects_false_accusations_on_clean_episodes():
    report = mixed_summary()
    report["clean_false_accusations"]["overall"]["accrual_company_v2"]["reconciliation"]["fp"] = 1
    with pytest.raises(ValueError, match="falsely accuses"):
        gate._assert_company_metrics(report)


def test_pair_gate_checks_both_causal_directions():
    assert gate._assert_pair_metrics(paired_summary()) == {
        "paired_comparisons": 6,
        "total_variants": 12,
        "audited_fault_issues": 8,
        "clean_false_accusations": 0,
    }


@pytest.mark.parametrize("wrong_key,wrong_value", [
    ("fault_tp", 7),
    ("both_correct", 5),
    ("clean_fp", 1),
    ("paired_accuracy", 0.5),
])
def test_pair_gate_rejects_incomplete_or_overaccusing_policy(wrong_key, wrong_value):
    report = paired_summary()
    report["policies"]["reconciliation"][wrong_key] = wrong_value
    with pytest.raises(ValueError):
        gate._assert_pair_metrics(report)


def test_failed_local_gate_is_never_reported_as_success_or_release_certification(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        gate, "_run",
        lambda *args, **kwargs: {"status": "fail", "exit_code": 1, "duration_sec": 0},
    )
    report_file = tmp_path / "result.json"
    status = gate.verify(mode="full", report_path=report_file, timeout=5)
    report = json.loads(report_file.read_text())
    assert status == 1 and report["success"] is False
    assert report["contest_certified"] is False
    assert report["docker_isolation_covered"] is False
    assert report["offline_bundle_covered"] is False
    assert set(report["stages"]) == {"pytest", "mixed_generator", "causal_pairs"}
    assert all(row["status"] == "fail" for row in report["stages"].values())
    assert "private" not in report_file.read_text()
    assert "issue_id" not in report_file.read_text()


def test_invalid_gate_mode_does_not_touch_report(tmp_path):
    result = tmp_path / "no.json"
    with pytest.raises(ValueError):
        gate.verify(mode="not-a-mode", report_path=result, timeout=5)
    assert not result.exists()
