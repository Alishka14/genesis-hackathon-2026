"""Six paired v2 clean/fault episodes over disjoint train/dev seeds."""
import json
import subprocess
import sys

import pytest

from ledgergym.episode_io import load_public_episode
from ledgergym.settlement_faults_v2 import validate_settlement_episode
from ledgergym.v2_pair_dataset import create_v2_causal_dataset, evaluate_v2_causal_dataset


def test_paired_v2_dataset_is_deterministic_and_labels_stay_private(tmp_path):
    one, two = tmp_path / "first", tmp_path / "second"
    index = create_v2_causal_dataset(one, seed=17)
    assert index == create_v2_causal_dataset(two, seed=17)
    assert len(index["train"]) == len(index["dev"]) == 3
    assert {(item["mode"]) for item in index["train"]} == {
        "duplicate_invoice", "payment_allocation", "duplicate_allocation"}
    assert {(item["mode"]) for item in index["dev"]} == {
        "duplicate_invoice", "payment_allocation", "duplicate_allocation"}
    seeds = [item["seed"] for split in ("train", "dev") for item in index[split]]
    assert len(seeds) == len(set(seeds)) == 6
    for split in ("train", "dev"):
        for pair in index[split]:
            variants = pair["variants"]
            assert set(variants) == {"clean", "faulty"}
            assert {path.rsplit("/", 1)[-1] for path in variants.values()} == {
                "variant-a", "variant-b"}
            clean_root = one / variants["clean"]
            fault_root = one / variants["faulty"]
            clean = load_public_episode(clean_root / "public")
            faulty = load_public_episode(fault_root / "public")
            assert clean["manifest"] == faulty["manifest"]
            assert clean["policy"] == faulty["policy"]
            assert clean["tables"]["fx"] == faulty["tables"]["fx"]
            assert clean["tables"]["ledger"] == faulty["tables"]["ledger"]
            assert set(x.name for x in (clean_root / "public").iterdir()) == {
                "manifest.json", "ledger.csv", "fx.csv", "policy.json",
                "invoices.jsonl", "payments.jsonl"}
            for root, expected_issue_count in [
                (clean_root, 0),
                (fault_root, 2 if pair["mode"] == "duplicate_allocation" else 1),
            ]:
                truth = json.loads((root / "private" / "truth.json").read_text())
                assert validate_settlement_episode(
                    load_public_episode(root / "public"), truth)["issue_count"] == expected_issue_count
                public_text = "".join(p.read_text() for p in (root / "public").iterdir())
                assert "private-" not in public_text and "issue_id" not in public_text
    assert {p.relative_to(one): p.read_bytes() for p in one.rglob("*") if p.is_file()} == {
        p.relative_to(two): p.read_bytes() for p in two.rglob("*") if p.is_file()}
    assert not (one / "public_pair_index.json").exists()
    assert (one / "private_pair_index.json").is_file()


def test_four_baselines_measure_causal_sensitivity(tmp_path):
    root = tmp_path / "dataset"
    create_v2_causal_dataset(root, seed=2026)
    summary = evaluate_v2_causal_dataset(root, tmp_path / "report")
    assert summary["pairs"] == 6
    assert summary["policies"]["reconciliation"]["both_correct"] == 6
    assert summary["policies"]["reconciliation"]["paired_accuracy"] == 1
    assert summary["policies"]["oracle"]["paired_accuracy"] == 1
    for name in ("seeded_random", "mark_all"):
        assert summary["policies"][name]["paired_accuracy"] == 0
        assert summary["policies"][name]["clean_fp"] >= 6
    assert summary["policies"]["reconciliation"]["fault_tp"] == 8
    assert summary["policies"]["oracle"]["fault_tp"] == 8
    assert len(summary["modes"]) == 6
    assert json.loads((tmp_path / "report/summary.json").read_text()) == summary
    assert "private-" not in json.dumps(summary)


def test_causal_dataset_cli(tmp_path):
    root = tmp_path / "pairs"
    result = subprocess.run([
        sys.executable, "-m", "ledgergym.v2_pair_dataset",
        str(root), "--seed", "81", "--evaluate",
    ], check=True, capture_output=True, text=True)
    output = json.loads(result.stdout)
    assert output["pairs"] == 6
    assert output["evaluation"]["policies"]["reconciliation"]["paired_accuracy"] == 1


def test_causal_dataset_never_overwrites(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    marker = root / "keep"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        create_v2_causal_dataset(root)
    assert marker.read_text() == "preserve"
