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
import psycopg
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


def setup_agent(principal: str) -> None:
    """Design 08 / infra step 9d: schema agent, role copilot_agent, review queue, LangGraph checkpoint tables,
    then GRANT copilot_agent to the app MI. Runs as the Entra admin; the app never runs DDL."""
    from pathlib import Path

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    settings = get_settings()
    cred = DefaultAzureCredential()
    with connect_as_me(settings, cred) as conn:
        conn.autocommit = True
        conn.execute(Path(__file__).with_name("agent_schema.sql").read_text())
    # LangGraph's migrations use unqualified table names (→ search_path) and CREATE INDEX CONCURRENTLY
    # (→ must be autocommit, outside a transaction).
    token = cred.get_token("https://ossrdbms-aad.database.windows.net/.default").token
    with psycopg.connect(host=settings.pg_host, dbname=settings.pg_database, user=settings.pg_user, password=token,
                         sslmode="require", autocommit=True, row_factory=dict_row,
                         options="-c search_path=agent -c statement_timeout=0") as conn:
        PostgresSaver(conn).setup()
    with connect_as_me(settings, cred) as conn:
        conn.autocommit = True
        conn.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agent TO copilot_agent")
        conn.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA agent TO copilot_agent")
        conn.execute(sql.SQL("GRANT copilot_agent TO {}").format(sql.Identifier(principal)))
        tables = [r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'agent' ORDER BY 1").fetchall()]
        member = conn.execute("SELECT pg_has_role(%s, 'copilot_agent', 'member'), "
                              "has_table_privilege(%s, 'public.awards', 'INSERT')", (principal, principal)).fetchone()
        print(f"agent tables={tables}; {principal}: copilot_agent={member[0]} can_insert_awards={member[1]}")


if __name__ == "__main__":
    commands = {"grant-app": grant_app, "setup-agent": setup_agent}
    if len(sys.argv) != 3 or sys.argv[1] not in commands:
        sys.exit("usage: python -m awards.admin {grant-app|setup-agent} <managed-identity-name>")
    commands[sys.argv[1]](sys.argv[2])
