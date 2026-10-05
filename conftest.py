import os
from types import SimpleNamespace

import nacl.signing
import pytest

# Test-only defaults. Production deployments must set these explicitly.
os.environ.setdefault("INDEXING_KEY", "thisisatest")

if "PASETO_PRIVATE_KEY" not in os.environ:
    _signing_key = nacl.signing.SigningKey.generate()
    os.environ["PASETO_PRIVATE_KEY"] = (
        bytes(_signing_key) + bytes(_signing_key.verify_key)
    ).hex()


@pytest.fixture(autouse=True)
def no_outbound_email(monkeypatch):
    """Tests must never reach Mailgun; record the requests instead."""
    sent = []

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        return SimpleNamespace(status_code=200, content=b"")

    monkeypatch.setattr("callisto_core.notification.api.requests.post", fake_post)
    monkeypatch.setattr("callisto_core.notification.tasks.requests.post", fake_post)
    return sent


@pytest.fixture(autouse=True)
def cheap_argon2id(settings):
    """Real Argon2id, with a small cost so the suite stays fast."""
    settings.ARGON2ID_MEMORY_COST = 1024
    settings.ARGON2ID_TIME_COST = 1
