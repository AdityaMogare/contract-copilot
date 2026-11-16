"""POST /ask (design 04 §3)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from opentelemetry import trace
from pydantic import BaseModel, Field

from app.auth import User, require_user
from app.config import Settings, get_settings
from app.guardrails.audit import audited
from app.guardrails.check import guard_input
from app.rag.answer import generate
from app.rag.retrieve import HopError, embed_query, hybrid_search
from app.errors import BLOCKED_TEXT, is_content_filter
from app.routers.smoke import _describe

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    part: str | None = Field(default=None, pattern=r"^\d{1,2}$")   # digits only: it goes into an OData filter


class Citation(BaseModel):
    n: int            # matches the [n] markers in `answer`
    citation: str
    url: str


class AskUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    attempts: int


class AskResponse(BaseModel):
    status: str
    answer: str
    citations: list[Citation]
    retrieved: int
    usage: AskUsage
    trace_id: str | None
    guardrail: str | None = None            # "prompt_shield" | "content_filter" when status == "blocked"
    redactions: list[dict] = []             # what PII was masked: categories and counts, never values


NO_USAGE = AskUsage(prompt_tokens=0, completion_tokens=0, reasoning_tokens=0, attempts=0)


def _trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request, settings: Settings = Depends(get_settings),
              user: User | None = Depends(require_user)) -> AskResponse:
    async with audited(request, user, "/ask") as ev:
        r = await _ask(body, request, settings, ev)
        ev.status = r.status
        ev.sources = [c.citation for c in r.citations]
        return r


async def _ask(body: AskRequest, request: Request, settings: Settings, ev) -> AskResponse:
    clients = request.app.state.clients
    span = trace.get_current_span()
    redactions: list[dict] = []
    try:
        async with asyncio.timeout(settings.rag_deadline_s):
            # Design 10: guard first, sequentially. Deviation from "parallel with the embedding": the embedding
            # and BM25 query must use the MASKED text, or PII would reach Azure OpenAI anyway.
            g = await guard_input(clients, settings, body.question)
            redactions, ev.question_masked = g.redactions, g.text
            ev.guardrails = {"prompt_attack": g.blocked, "redactions": g.redactions}
            if g.blocked:
                span.set_attribute("rag.status", "blocked")
                return AskResponse(status="blocked", answer=BLOCKED_TEXT, citations=[], retrieved=0, usage=NO_USAGE,
                                   trace_id=_trace_id(), guardrail="prompt_shield", redactions=redactions)
            vector = await embed_query(clients, settings, g.text)
            chunks = await hybrid_search(clients, settings, g.text, vector, body.part)
            result = await generate(clients, settings, g.text, chunks)
    except TimeoutError:
        raise HTTPException(504, detail={"error": f"deadline {settings.rag_deadline_s:g}s exceeded"})
    except HopError as e:
        if is_content_filter(e.cause):
            span.set_attribute("rag.status", "blocked")
            return AskResponse(status="blocked", answer=BLOCKED_TEXT, citations=[], retrieved=0, usage=NO_USAGE,
                               trace_id=_trace_id(), guardrail="content_filter", redactions=redactions)
        span.set_attribute("rag.failed_hop", e.hop)
        raise HTTPException(503, detail={"hop": e.hop, "error": _describe(e.cause)})

    span.set_attribute("rag.status", result.status)
    span.set_attribute("rag.retrieved", len(chunks))
    span.set_attribute("rag.cited", len(result.cited))
    span.set_attribute("rag.validation_failed", result.validation_failed)
    u = result.usage
    return AskResponse(
        status=result.status,
        answer=result.answer,
        citations=[Citation(n=c.n, citation=c.citation, url=c.url) for c in result.cited],
        retrieved=len(chunks),
        usage=AskUsage(prompt_tokens=u.prompt_tokens, completion_tokens=u.completion_tokens,
                       reasoning_tokens=u.reasoning_tokens, attempts=u.attempts),
        trace_id=_trace_id(),
        redactions=redactions,
    )
