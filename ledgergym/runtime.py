"""Trusted episode construction; never import this inside an untrusted agent."""
import secrets
from .generator import generate_episode
from .score import evaluate
from .record_ids import addressable_ids


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
    public_ids = addressable_ids(public)

    def evaluator(findings, steps):
        return evaluate(truth['issues'], findings, public_ids, steps)

    return public, evaluator
