import json
import pytest
from ledgergym.episode_io import export_episode, load_public_episode
from ledgergym.world import make_episode
from ledgergym.payment_world import make_payment_episode
from ledgergym.fx_world import make_fx_episode
from ledgergym.period_world import make_period_episode


@pytest.mark.parametrize('factory', [lambda: make_episode(42), lambda: make_payment_episode(42, 'partial'), lambda: make_fx_episode(42, 'wrong_rate'), lambda: make_period_episode(42, True)])
def test_round_trip_public_data_and_separate_private_files(tmp_path, factory):
    public, truth = factory()
    root = tmp_path / 'episode'
    export_episode(root, public, truth, seed=42)
    assert load_public_episode(root / 'public') == public
    assert json.loads((root / 'private' / 'truth.json').read_text()) == truth
    assert (root / 'private' / 'provenance.json').exists()
    assert sorted(p.name for p in (root / 'public').iterdir()) == ['fx.csv', 'invoices.jsonl', 'ledger.csv', 'manifest.json', 'payments.jsonl', 'policy.json']
    combined_public = ''.join(p.read_text() for p in (root / 'public').iterdir())
    assert 'issue_id' not in combined_public and 'expected_amount_minor' not in combined_public
    if truth['issues']:
        assert truth['issues'][0]['issue_id'] not in combined_public


def test_export_is_byte_reproducible_and_wont_replace_existing(tmp_path):
    public, truth = make_fx_episode(99, 'wrong_date')
    first, second = tmp_path / 'one', tmp_path / 'two'
    export_episode(first, public, truth, seed=99)
    export_episode(second, public, truth, seed=99)
    first_files = {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}
    second_files = {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()}
    assert first_files == second_files
    with pytest.raises(FileExistsError):
        export_episode(first, public, truth, seed=99)
    assert {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()} == first_files
