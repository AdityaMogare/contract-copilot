"""POST /awards/query (design 07 §3): returns data and the SQL that produced it, not prose."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from opentelemetry import trace
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
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


@router.post("/awards/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request, settings: Settings = Depends(get_settings)) -> QueryResponse:
    span = trace.get_current_span()
    try:
        async with asyncio.timeout(settings.sql_deadline_s):
            r = await answer(request.app.state.clients, settings, body.question)
    except TimeoutError:
        raise HTTPException(504, detail={"error": f"deadline {settings.sql_deadline_s:g}s exceeded"})
    except HopError as e:
        if is_content_filter(e.cause):
            span.set_attribute("sql.status", "blocked")
            return QueryResponse(status="blocked", explanation=BLOCKED_TEXT, sql="", columns=[], rows=[], row_count=0,
                                 truncated=False, attempts=0, usage={}, trace_id=_trace_id())
        span.set_attribute("sql.failed_hop", e.hop)
        raise HTTPException(503, detail={"hop": e.hop, "error": _describe(e.cause)})
    span.set_attribute("sql.status", r.status)
    span.set_attribute("sql.attempts", r.attempts)
    return QueryResponse(status=r.status, explanation=r.explanation, sql=r.sql, columns=r.columns, rows=r.rows,
                         row_count=len(r.rows), truncated=r.truncated, attempts=r.attempts, usage=r.usage,
                         trace_id=_trace_id())
