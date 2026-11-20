import copy
import random
import pytest
from ledgergym.world import make_episode, validate_episode
from ledgergym.payment_world import make_payment_episode, validate_payment_episode
from ledgergym.fx_world import make_fx_episode, validate_fx_episode
from ledgergym.period_world import make_period_episode, validate_period_episode


def remap(value, mapping):
    if isinstance(value, dict):
        return {k: remap(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [remap(v, mapping) for v in value]
    return mapping.get(value, value) if isinstance(value, str) else value


@pytest.mark.parametrize('factory,validator', [
    (lambda: make_episode(11, True), validate_episode),
    (lambda: make_payment_episode(11, 'partial'), validate_payment_episode),
    (lambda: make_fx_episode(11, 'wrong_rate'), validate_fx_episode),
    (lambda: make_period_episode(11, True), validate_period_episode),
])
def test_preflight_survives_bijective_id_remap_and_row_shuffle(factory, validator):
    public, truth = factory()
    identifiers = set()
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if (key.endswith('_id') or key == 'service_ref') and isinstance(item, str) and item.startswith('id-'):
                    identifiers.add(item)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(public['tables'])
    mapping = {value: f'remapped-{n:03}' for n, value in enumerate(sorted(identifiers))}
    updated_public = remap(copy.deepcopy(public), mapping)
    updated_truth = remap(copy.deepcopy(truth), mapping)
    rng = random.Random(11)
    for rows in updated_public['tables'].values():
        rng.shuffle(rows)
    validator(updated_public, updated_truth)
