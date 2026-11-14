"""Entra ID access-token validation for incoming requests (design 02 revision).

A request must carry `Authorization: Bearer <JWT>` issued by our tenant for our API. We verify:
  signature (tenant's public signing keys, fetched once and cached) · iss · aud · exp/nbf · scp.
No secret is involved: validation only needs Microsoft's PUBLIC keys.

401 = we can't trust who you are (missing, malformed, bad signature, wrong iss/aud, expired).
403 = we know who you are, but the token lacks the required scope.
"""

from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import Settings, get_settings


class User(BaseModel):
    oid: str
    name: str | None = None


@lru_cache
def _jwks_client(tenant_id: str) -> jwt.PyJWKClient:
    # Cached per process; PyJWKClient also caches keys and refetches when it sees an unknown `kid`
    # (Entra rotates signing keys).
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def require_user(request: Request, settings: Settings = Depends(get_settings)) -> User | None:
    """FastAPI dependency. Sync on purpose: FastAPI runs it in a threadpool, so the (rare,
    cached) blocking JWKS fetch doesn't stall the event loop."""
    if not settings.auth_required:
        return None
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("missing bearer token")
    try:
        key = _jwks_client(settings.auth_tenant_id).get_signing_key_from_jwt(token)  # type: ignore[arg-type]
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],  # pin it: never let the token choose (e.g. "none")
            audience=settings.auth_audience,
            issuer=f"https://login.microsoftonline.com/{settings.auth_tenant_id}/v2.0",
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized(f"invalid token: {type(exc).__name__}") from exc
    if settings.auth_scope not in str(claims.get("scp", "")).split():
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"token lacks scope {settings.auth_scope}")
    return User(oid=claims["oid"], name=claims.get("name"))
