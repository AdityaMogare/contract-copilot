"""Hop 4 (design 07): run validated SQL. Layer 3: a READ ONLY transaction, as copilot_reader, 5 s timeout,
always rolled back. Applies locally too, where the connecting user is the Entra admin."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from opentelemetry import trace

tracer = trace.get_tracer(__name__)


def _json(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


async def run_readonly(pool, sql: str, timeout_s: float, params: tuple | None = None) -> tuple[list[str], list[list]]:
    with tracer.start_as_current_span("postgres") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", sql[:2000])
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                await conn.execute("SET TRANSACTION READ ONLY")
                await conn.execute("SET LOCAL ROLE copilot_reader")
                await conn.execute(f"SET LOCAL statement_timeout = '{int(timeout_s * 1000)}ms'")
                cur = await conn.execute(sql, params)
                columns = [d.name for d in (cur.description or [])]
                rows = [[_json(v) for v in r] for r in await cur.fetchall()]
        span.set_attribute("db.rows", len(rows))
        return columns, rows
