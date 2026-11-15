"""Async Postgres pool authenticated with Entra tokens (design 06 hops 7–8).

Postgres checks the token only when a connection is OPENED, and tokens live ~60–90 min. So:
- every new pooled connection fetches a token (the credential caches it until near expiry),
- max_lifetime (30 min) retires connections well before their token would matter for a reconnect,
- min_size=0: with scale-to-zero apps and a stopped server, don't hold idle connections.
Each session is forced read-only with a statement timeout, in addition to the DB role's own settings.
"""

from __future__ import annotations

import psycopg
from azure.identity.aio import DefaultAzureCredential
from psycopg_pool import AsyncConnectionPool

from app.config import Settings

PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
SESSION_OPTS = "-c default_transaction_read_only=on -c statement_timeout=5000"


def make_pool(settings: Settings, credential: DefaultAzureCredential) -> AsyncConnectionPool | None:
    if not (settings.pg_host and settings.pg_user):
        return None

    class EntraConnection(psycopg.AsyncConnection):
        @classmethod
        async def connect(cls, conninfo: str = "", **kwargs):
            kwargs["password"] = (await credential.get_token(PG_SCOPE)).token
            return await super().connect(conninfo, **kwargs)

    return AsyncConnectionPool(
        conninfo="",
        kwargs={"host": settings.pg_host, "dbname": settings.pg_database, "user": settings.pg_user,
                "sslmode": "require", "connect_timeout": 10, "options": SESSION_OPTS},
        connection_class=EntraConnection,
        min_size=0, max_size=4, max_lifetime=1800, timeout=15, open=False,
    )
