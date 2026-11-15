"""The schema text the model sees, built FROM the database (design 07 §2), so it can't drift from 06's tables.

Columns + their COMMENTs, plus the exact value list of every low-cardinality text column (≤ 20 distinct):
the probe showed the model guesses codes otherwise.
"""

from __future__ import annotations

import asyncio

from opentelemetry import trace

from app.sql.validate import ALLOWED_TABLES

MAX_VALUES = 20
tracer = trace.get_tracer(__name__)
_lock = asyncio.Lock()
_card: str | None = None

COLUMNS_SQL = """
SELECT c.table_name, c.column_name, c.data_type,
       col_description(format('%%I', c.table_name)::regclass, c.ordinal_position)
FROM information_schema.columns c
WHERE c.table_schema = 'public' AND c.table_name = ANY(%s)
ORDER BY c.table_name, c.ordinal_position
"""


def render(columns: list[tuple], values: dict[str, list[str]], table_comments: dict[str, str]) -> str:
    out, current = [], None
    for table, column, dtype, comment in columns:
        if table != current:
            current = table
            out.append(f"\nTABLE {table}" + (f"  -- {table_comments[table]}" if table_comments.get(table) else ""))
        line = f"  {column} {dtype}" + (f"  -- {comment}" if comment else "")
        if f"{table}.{column}" in values:
            line += f"  VALUES: {values[f'{table}.{column}']}"
        out.append(line)
    return "\n".join(out).strip()


async def build(conn) -> str:
    tables = sorted(ALLOWED_TABLES)
    columns = await (await conn.execute(COLUMNS_SQL, (tables,))).fetchall()
    table_comments = {t: (await (await conn.execute("SELECT obj_description(%s::regclass)", (t,))).fetchone())[0]
                      for t in tables}
    values: dict[str, list[str]] = {}
    for table, column, dtype, _ in columns:
        if dtype != "text":
            continue
        # Identifiers come from information_schema for allowlisted tables only, never from user input.
        q = f'SELECT DISTINCT "{column}" FROM {table} WHERE "{column}" IS NOT NULL LIMIT {MAX_VALUES + 1}'
        distinct = [r[0] for r in await (await conn.execute(q)).fetchall()]
        if len(distinct) <= MAX_VALUES:
            values[f"{table}.{column}"] = sorted(distinct)
    return render(columns, values, table_comments)


async def get(pool) -> str:
    """Built on first use and cached: building at startup would fail whenever Postgres is stopped."""
    global _card
    if _card is None:
        async with _lock:
            if _card is None:
                # First request after a deploy: opens a pooled connection (MI token for the ossrdbms scope)
                # and runs ~30 DISTINCT queries. psycopg isn't auto-instrumented, so this span makes the
                # ~1.3 s visible in the trace (seen as an unexplained gap on the first live call).
                with tracer.start_as_current_span("schema_card.build") as span:
                    async with pool.connection() as conn:
                        _card = await build(conn)
                    span.set_attribute("schema_card.chars", len(_card))
    return _card


def reset() -> None:
    global _card
    _card = None
