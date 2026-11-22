"""External callers that omit our private `scenario` key get the company model."""
import filecmp
import json
import os

import pytest

import judge_adapter
from ledgergym import generator
from ledgergym.canonical import JudgeEnv


@pytest.mark.parametrize("config", [None, {}])
def test_missing_config_generates_the_company_model(tmp_path, config):
    judge_adapter.generate_episode(3, config, tmp_path / "default")
    judge_adapter.generate_episode(3, {"scenario": "company"}, tmp_path / "explicit")
    public = sorted(os.listdir(tmp_path / "explicit" / "public"))
    assert sorted(os.listdir(tmp_path / "default" / "public")) == public
    for name in public:
        assert filecmp.cmp(tmp_path / "default" / "public" / name,
                           tmp_path / "explicit" / "public" / name, shallow=False)
    assert (tmp_path / "default" / "private" / "provenance.json").is_file()


def test_company_keys_without_scenario_select_company(tmp_path):
    config = {"postings": 500, "documents": 50, "faults": {"duplicate_invoice": 2}}
    judge_adapter.generate_episode(4, config, tmp_path / "ep")
    truth = json.loads((tmp_path / "ep" / "private" / "truth.json").read_text())
    assert [issue["type"] for issue in truth["issues"]] == ["duplicate_invoice"] * 2
    normalized = generator._default_scenario(config)
    assert normalized == {"scenario": "company", **config}


def test_unknown_keys_and_named_scenarios_keep_previous_behaviour(tmp_path):
    with pytest.raises(ValueError):
        judge_adapter.generate_episode(1, {"n_faults": 3}, tmp_path / "bad")
    assert generator._default_scenario({"scenario": "duplicate_invoice"}) == {"scenario": "duplicate_invoice"}
    # The development generator keeps its documented strict contract.
    with pytest.raises(ValueError):
        generator.generate_episode(1, {})


@pytest.mark.parametrize("config", [{"mode": "train"}, {"mode": "train", "team_config": {}}])
def test_train_reset_without_team_config_uses_company_default(config):
    obs, info = JudgeEnv().reset(5, config)
    assert obs["remaining_steps"] == 100 and info == {}
