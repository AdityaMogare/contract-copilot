"""POST /awards/query (design 07 §3): returns data and the SQL that produced it, not prose."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from opentelemetry import trace
from pydantic import BaseModel, Field

from app.auth import User, require_user
from app.config import Settings, get_settings
from app.guardrails.audit import audited
from app.guardrails.check import guard_input
from app.rag.retrieve import HopError
from app.routers.ask import _trace_id
from app.errors import BLOCKED_TEXT, is_content_filter
from app.routers.smoke import _describe
from app.sql.answer import answer

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class QueryResponse(BaseModel):
    status: str
    explanation: str
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    attempts: int
    usage: dict
    trace_id: str | None
    guardrail: str | None = None
    redactions: list[dict] = []


def _blocked(guardrail: str, redactions: list[dict]) -> QueryResponse:
    return QueryResponse(status="blocked", explanation=BLOCKED_TEXT, sql="", columns=[], rows=[], row_count=0,
                         truncated=False, attempts=0, usage={}, trace_id=_trace_id(), guardrail=guardrail,
                         redactions=redactions)


@router.post("/awards/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request, settings: Settings = Depends(get_settings),
                user: User | None = Depends(require_user)) -> QueryResponse:
    async with audited(request, user, "/awards/query") as ev:
        r = await _query(body, request, settings, ev)
        ev.status = r.status
        ev.sql = [r.sql] if r.sql else []
        return r


async def _query(body: QueryRequest, request: Request, settings: Settings, ev) -> QueryResponse:
    span = trace.get_current_span()
    redactions: list[dict] = []
    try:
        async with asyncio.timeout(settings.sql_deadline_s):
            g = await guard_input(request.app.state.clients, settings, body.question)
            redactions, ev.question_masked = g.redactions, g.text
            ev.guardrails = {"prompt_attack": g.blocked, "redactions": g.redactions}
            if g.blocked:
                span.set_attribute("sql.status", "blocked")
                return _blocked("prompt_shield", redactions)
            r = await answer(request.app.state.clients, settings, g.text)
    except TimeoutError:
        raise HTTPException(504, detail={"error": f"deadline {settings.sql_deadline_s:g}s exceeded"})
    except HopError as e:
        if is_content_filter(e.cause):
            span.set_attribute("sql.status", "blocked")
            return _blocked("content_filter", redactions)
        span.set_attribute("sql.failed_hop", e.hop)
        raise HTTPException(503, detail={"hop": e.hop, "error": _describe(e.cause)})
    span.set_attribute("sql.status", r.status)
    span.set_attribute("sql.attempts", r.attempts)
    return QueryResponse(status=r.status, explanation=r.explanation, sql=r.sql, columns=r.columns, rows=r.rows,
                         row_count=len(r.rows), truncated=r.truncated, attempts=r.attempts, usage=r.usage,
                         trace_id=_trace_id(), redactions=redactions)
