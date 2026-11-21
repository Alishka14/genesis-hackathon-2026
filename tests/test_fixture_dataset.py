import json
import pytest
from ledgergym.fixture_dataset import create_fixture_dataset
from ledgergym.episode_io import load_public_episode


def test_twenty_reproducible_fixtures_and_no_private_in_public_index(tmp_path):
    root1, root2 = tmp_path / 'a', tmp_path / 'b'
    create_fixture_dataset(root1)
    create_fixture_dataset(root2)
    manifest = json.loads((root1 / 'index.json').read_text())
    assert manifest['kind'] == 'development_fixtures_not_benchmark'
    assert len(manifest['train']) == len(manifest['dev']) == 10
    seen_ids = set()
    for split in ('train', 'dev'):
        for entry in manifest[split]:
            episode = root1 / entry['path']
            public = load_public_episode(episode / 'public')
            assert public['manifest']['episode_id'] == entry['episode_id']
            assert entry['episode_id'] not in seen_ids
            seen_ids.add(entry['episode_id'])
            assert (episode / 'private' / 'truth.json').exists()
            assert (episode / 'private' / 'provenance.json').exists()
    first = {p.relative_to(root1): p.read_bytes() for p in root1.rglob('*') if p.is_file()}
    second = {p.relative_to(root2): p.read_bytes() for p in root2.rglob('*') if p.is_file()}
    assert first == second
    index_text = (root1 / 'index.json').read_text()
    assert 'private' not in index_text and 'seed' not in index_text and 'scenario' not in index_text


def test_fixture_dataset_does_not_replace_existing_directory(tmp_path):
    existing = tmp_path / 'existing'
    existing.mkdir()
    marker = existing / 'marker.txt'
    marker.write_text('preserve')
    with pytest.raises(FileExistsError):
        create_fixture_dataset(existing)
    assert marker.read_text() == 'preserve'
