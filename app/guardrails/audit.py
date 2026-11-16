"""Append-only audit log (design 10 §1). The app's role has INSERT only on agent.audit_log (no UPDATE/DELETE/
SELECT), so it can't rewrite or read back history. Writes are best-effort: a failed audit write is recorded on the
span (audit.failed) instead of failing the user's request (decision in design 10, After building)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import HTTPException
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

INSERT = """INSERT INTO agent.audit_log (user_oid, endpoint, thread_id, question_masked, status, guardrails,
            tools, sql, sources, review_ids, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""


@dataclass
class AuditEvent:
    endpoint: str
    user_oid: str | None
    question_masked: str | None = None     # never the raw question: set only after PII masking
    status: str = "error"
    thread_id: str | None = None
    guardrails: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    sql: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    review_ids: list[int] = field(default_factory=list)
    trace_id: str | None = None


async def record(pool, ev: AuditEvent) -> bool:
    with tracer.start_as_current_span("audit.insert") as span:
        if pool is None:
            span.set_attribute("audit.failed", "no pool")
            return False
        try:
            async with asyncio.timeout(3):
                async with pool.connection() as conn:
                    await conn.execute(INSERT, (ev.user_oid, ev.endpoint, ev.thread_id, ev.question_masked, ev.status,
                                                json.dumps(ev.guardrails), ev.tools, ev.sql, ev.sources, ev.review_ids,
                                                ev.trace_id))
            return True
        except Exception as e:
            span.set_attribute("audit.failed", type(e).__name__)
            return False


@asynccontextmanager
async def audited(request, user, endpoint: str):
    """Yields an AuditEvent; writes it when the request ends, including 503/504 (status http_<code>)."""
    ctx = trace.get_current_span().get_span_context()
    ev = AuditEvent(endpoint=endpoint, user_oid=getattr(user, "oid", None) or "local-dev",
                    trace_id=format(ctx.trace_id, "032x") if ctx.is_valid else None)
    try:
        yield ev
    except HTTPException as e:
        ev.status = f"http_{e.status_code}"
        raise
    finally:
        await record(getattr(request.app.state.clients, "pg_agent", None), ev)
