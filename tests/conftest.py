import os

# Before any test module imports app.main: unit tests must never export telemetry to Azure.
os.environ["OTEL_SDK_DISABLED"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient

from app.config import get_settings

FAKE_ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://fake-ais.example.com/",
    "SEARCH_ENDPOINT": "https://fake-srch.example.com",
    "KEY_VAULT_URL": "https://fake-kv.example.com/",
    "STORAGE_ACCOUNT_URL": "https://fake-st.example.com",
    "SMOKE_TIMEOUT_S": "0.2",
    "GUARDRAILS_ENABLED": "false",  # tests/test_guardrails.py turns it on with faked shield/PII calls
    "AUTH_REQUIRED": "false",  # auth is fail-closed by default; tests/test_auth.py turns it on
}


@pytest.fixture
def client(monkeypatch):
    """App with fake, non-routable endpoints. Unit tests never reach Azure: checks are faked."""
    for k, v in FAKE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir("/")  # don't pick up the real .env
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
