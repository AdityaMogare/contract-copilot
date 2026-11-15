"""Create the app's Postgres login and make it read-only (infra step 9c, design 06). Run as the Entra admin.

uv run python -m awards.admin grant-app id-app-cczq9h

- pgaadauth_create_principal maps an Entra principal (here: the user-assigned managed identity, by NAME)
  to a Postgres login role. Azure resolves the name against Entra; no password exists.
- Membership in copilot_reader gives SELECT on awards/transactions only (schema.sql).
- Role-level settings must be on the LOGIN role: Postgres doesn't apply a group role's ALTER ROLE … SET
  to its members. So read-only + statement timeout are set on the MI's role itself.
"""

from __future__ import annotations

import sys

from azure.identity import DefaultAzureCredential
from psycopg import sql

from app.config import get_settings
from awards.load import connect_as_me


def grant_app(principal: str) -> None:
    settings = get_settings()
    with connect_as_me(settings.model_copy(update={"pg_database": "postgres"}), DefaultAzureCredential()) as conn:
        conn.autocommit = True
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (principal,)).fetchone()
        if not exists:   # is_admin=false, is_mfa=false; type inferred (service principal / MI)
            conn.execute("SELECT * FROM pgaadauth_create_principal(%s, false, false)", (principal,))
            print(f"created principal {principal}")
    with connect_as_me(settings, DefaultAzureCredential()) as conn:
        conn.autocommit = True
        role = sql.Identifier(principal)
        conn.execute(sql.SQL("GRANT copilot_reader TO {}").format(role))
        conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(role))
        row = conn.execute("SELECT pg_has_role(%s, 'copilot_reader', 'member'), "
                           "(SELECT rolconfig FROM pg_roles WHERE rolname = %s)", (principal, principal)).fetchone()
        print(f"{principal}: copilot_reader={row[0]} config={row[1]}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "grant-app":
        sys.exit("usage: python -m awards.admin grant-app <managed-identity-name>")
    grant_app(sys.argv[2])
