"""Token validation tests: we mint our own RSA-signed JWTs and point the JWKS lookup at our
public key, so every rule in app/auth.py is exercised without calling Entra."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth
from app.config import get_settings
from app.main import app
from app.routers.smoke import get_checks

TENANT = "11111111-1111-1111-1111-111111111111"
AUDIENCE = "22222222-2222-2222-2222-222222222222"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return jwt.PyJWK.from_dict(
            {**jwt.algorithms.RSAAlgorithm.to_jwk(_key.public_key(), as_dict=True), "kid": "k1", "alg": "RS256"}
        )


def _token(key=_key, **overrides):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "exp": now + 600, "nbf": now - 10, "iat": now - 10,
              "scp": "access_as_user", "oid": "user-oid", "name": "Test User", **overrides}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


async def _ok(clients, settings):
    return "fine"


@pytest.fixture
def authed_client(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("AUTH_TENANT_ID", TENANT)
    monkeypatch.setenv("AUTH_AUDIENCE", AUDIENCE)
    get_settings.cache_clear()
    monkeypatch.setattr(auth, "_jwks_client", lambda tenant: _FakeJwks())
    app.dependency_overrides[get_checks] = lambda: {"a": _ok}
    yield client
    get_settings.cache_clear()


def _get(c, token=None, raw=None):
    headers = {"Authorization": raw if raw is not None else f"Bearer {token}"} if (token or raw) else {}
    return c.get("/smoke", headers=headers)


def test_valid_token_passes(authed_client):
    assert _get(authed_client, _token()).status_code == 200


def test_health_needs_no_token(authed_client):
    assert authed_client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "case, kwargs",
    [
        ("no header", None),
        ("not bearer", "raw:Basic abc"),
        ("garbage", "raw:Bearer not-a-jwt"),
        ("wrong audience", {"aud": "api://someone-else"}),
        ("wrong issuer", {"iss": "https://login.microsoftonline.com/other-tenant/v2.0"}),
        ("expired", {"exp": int(time.time()) - 60}),
        ("forged signature", "key:other"),
    ],
)
def test_untrusted_tokens_get_401(authed_client, case, kwargs):
    if kwargs is None:
        r = _get(authed_client)
    elif isinstance(kwargs, str) and kwargs.startswith("raw:"):
        r = _get(authed_client, raw=kwargs[4:])
    elif kwargs == "key:other":
        r = _get(authed_client, _token(key=_other_key))
    else:
        r = _get(authed_client, _token(**kwargs))
    assert r.status_code == 401, case
    assert r.headers.get("www-authenticate") == "Bearer"


def test_missing_scope_gets_403(authed_client):
    assert _get(authed_client, _token(scp="something_else")).status_code == 403


def test_alg_none_is_rejected(authed_client):
    unsigned = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 600,
                           "scp": "access_as_user", "oid": "x"}, key=None, algorithm="none")
    assert _get(authed_client, unsigned).status_code == 401


def test_auth_required_without_config_refuses_to_start(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.delenv("AUTH_TENANT_ID", raising=False)
    monkeypatch.delenv("AUTH_AUDIENCE", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.example.com/")
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://x.example.com")
    monkeypatch.setenv("KEY_VAULT_URL", "https://x.example.com/")
    monkeypatch.setenv("STORAGE_ACCOUNT_URL", "https://x.example.com")
    monkeypatch.chdir("/")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_REQUIRED=true needs"):
        with TestClient(app):
            pass
    get_settings.cache_clear()


def test_ask_requires_token(authed_client):
    assert authed_client.post("/ask", json={"question": "x"}).status_code == 401


def test_awards_query_requires_token(authed_client):
    assert authed_client.post("/awards/query", json={"question": "x"}).status_code == 401


def test_reviews_require_token(authed_client):
    assert authed_client.get("/reviews").status_code == 401
    assert authed_client.post("/awards/FA1/competition-check").status_code == 401
