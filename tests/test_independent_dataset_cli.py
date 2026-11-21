"""Trusted aggregate audit CLI must reject malformed labels without leaking them."""
import json
import pytest

from ledgergym.company_dataset import create_company_dataset
from ledgergym.independent_dataset_audit import audit_dataset


def test_actual_mixed_dataset_independently_reconciled_without_private_output(tmp_path):
    dataset = tmp_path / "trusted"
    create_company_dataset(dataset, seed=2027, include_settlement_hard_negatives=True)
    report = audit_dataset(dataset)
    assert report["status"] == "PASS"
    assert report["episodes_audited"] == 20
    assert report["accounting_models"] == {
        "accrual_company_v1": 16, "accrual_company_v2": 4}
    assert report["independent_external_accountant"] is False
    assert report["contest_certified"] is False
    assert report["private_truth_exported"] is False
    assert "issue_id" not in json.dumps(report)
    assert "seed" not in json.dumps(report)

    # The second audit must fail if a malicious source silently changes truth.
    source = dataset / "train" / "episode-00" / "private" / "truth.json"
    truth = json.loads(source.read_text(encoding="utf-8"))
    if truth["issues"]:
        truth["issues"][0]["expected_amount_minor"] += 1
    else:
        truth["issues"] = [{
            "issue_id": "private-forgery", "type": "duplicate_invoice",
            "affected_ids": ["forged-a", "forged-b"], "currency": "KZT",
            "expected_amount_minor": 1, "allowed_evidence_sets": [["forged-a"]],
        }]
    source.write_text(json.dumps(truth), encoding="utf-8")
    with pytest.raises(ValueError):
        audit_dataset(dataset)


def test_independent_audit_rejects_index_path_traversal(tmp_path):
    dataset = tmp_path / "trusted"
    create_company_dataset(dataset, seed=101, include_settlement_hard_negatives=False)
    index = json.loads((dataset / "index.json").read_text(encoding="utf-8"))
    index["dev"][0]["path"] = "dev/../private"
    (dataset / "index.json").write_text(json.dumps(index))
    with pytest.raises(ValueError, match="untrusted index path"):
        audit_dataset(dataset)
