import os
from types import SimpleNamespace

import pytest

# Test-only defaults. Production deployments must set these explicitly.
os.environ.setdefault("INDEXING_KEY", "thisisatest")


@pytest.fixture(autouse=True)
def no_outbound_email(monkeypatch):
    """Tests must never reach Mailgun; record the requests instead."""
    sent = []

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        return SimpleNamespace(status_code=200, content=b"")

    # email goes out only through notification.tasks
    monkeypatch.setattr("callisto_core.notification.tasks.requests.post", fake_post)
    return sent


@pytest.fixture(autouse=True)
def cheap_argon2id(settings):
    """Real Argon2id, with a small cost so the suite stays fast."""
    settings.ARGON2ID_MEMORY_COST = 1024
    settings.ARGON2ID_TIME_COST = 1


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Save browser screenshots and HTML for failed selenium tests."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        dump = getattr(getattr(item, "instance", None), "dump_browser_state", None)
        if dump:
            try:
                dump()
            except Exception as exc:  # never hide the original failure
                print(f"could not save browser state: {exc!r}")
