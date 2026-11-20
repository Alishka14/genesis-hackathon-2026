"""Trusted episode construction; never import this inside an untrusted agent."""
import secrets
from .generator import generate_episode
from .score import evaluate


def create_episode(seed=None, config=None):
    """Return public data and an evaluator bound to this episode's private truth.

    This callback boundary is for local development, not process isolation.
    Explicit seed/config reproduce a small fixture; omitted seed is fresh.
    """
    if seed is None:
        seed = secrets.randbits(128)
    if config is None:
        config = {'scenario': 'duplicate_invoice', 'fault': True}
    public, truth = generate_episode(seed, config)
    public_ids = {
        value for rows in public['tables'].values() for row in rows
        for key, value in row.items() if key.endswith('_id') and isinstance(value, str)
    }

    def evaluator(findings, steps):
        return evaluate(truth['issues'], findings, public_ids, steps)

    return public, evaluator
