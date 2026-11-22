# LedgerGym verification container (FinTech case §07/§09: container instructions
# and a single check command). Same pinned base image as the agent sandbox.
#
#   docker build -t ledgergym .
#   docker run --rm ledgergym                      # one-command check
#   docker run --rm ledgergym python scripts/jury_simulation.py
#   docker run --rm ledgergym python -m ledgergym.agent_diagnostics --held-out 30
#
# Offline build: first run `python3 scripts/prepare_wheelhouse.py ./ledgergym-wheelhouse`
# (needs network once). If that folder exists, the build installs from it with
# --no-index; otherwise it downloads the same hash-pinned wheels from PyPI.
FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /opt/ledgergym

# Test-only dependencies, exact versions and SHA-256 hashes. The runtime itself
# uses only the Python standard library.
COPY requirements-dev.lock /tmp/requirements-dev.lock
COPY requirements-dev.lock ledgergym-wheelhouse* /tmp/wheels/
RUN if ls /tmp/wheels/*.whl >/dev/null 2>&1; then \
        pip install --no-index --find-links /tmp/wheels --require-hashes --only-binary=:all: --no-deps -r /tmp/requirements-dev.lock; \
    else \
        pip install --require-hashes --only-binary=:all: --no-deps -r /tmp/requirements-dev.lock; \
    fi \
    && rm -rf /tmp/wheels /tmp/requirements-dev.lock /root/.cache

COPY . .

RUN useradd --create-home --uid 10001 ledgergym && chown -R ledgergym /opt/ledgergym
USER ledgergym

# Runs all tests (Docker-isolation tests skip inside this container; they run on
# a host with Docker), the 10+10 generation with 60 exact replays, 6 causal
# clean/fault pairs and the check that no evaluator-only file is shipped.
CMD ["python", "scripts/verify_integration.py", "--mode", "focused", "--report", "/tmp/ledgergym-report.json"]
