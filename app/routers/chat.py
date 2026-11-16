"""POST /chat (design 08 §3): the agent, with memory per thread_id (LangGraph checkpoints in schema agent)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from opentelemetry import trace
from pydantic import BaseModel, Field

from app.agent.graph import SOURCE_ID, build_graph, make_models
from app.agent.tools import SourceBook, build_tools
from app.auth import User, require_user
from app.config import Settings, get_settings
from app.guardrails.audit import audited
from app.guardrails.check import guard_input
from app.rag.retrieve import HopError
from app.routers.ask import _trace_id
from app.errors import BLOCKED_TEXT, is_content_filter
from app.routers.smoke import _describe

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: uuid.UUID | None = None


def _blocked(thread_id: str, guardrail: str, redactions: list[dict], model_calls: int = 0) -> dict:
    return {"thread_id": thread_id, "status": "blocked", "guardrail": guardrail, "redactions": redactions,
            "sources": [], "review_items": [], "answer": BLOCKED_TEXT, "tool_calls_this_turn": 0,
            "usage": {"model_calls": model_calls}, "trace_id": _trace_id()}


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, settings: Settings = Depends(get_settings),
               user: User | None = Depends(require_user)):
    async with audited(request, user, "/chat") as ev:
        out = await _chat(body, request, settings, ev)
        ev.status = out["status"]
        return out


async def _chat(body: ChatRequest, request: Request, settings: Settings, ev) -> dict:
    clients = request.app.state.clients
    if clients.pg_agent is None:
        raise HTTPException(503, detail={"hop": "postgres", "error": "memory store (Postgres) not configured"})
    thread_id = ev.thread_id = str(body.thread_id or uuid.uuid4())
    span = trace.get_current_span()
    span.set_attribute("chat.thread_id", thread_id)

    # Design 10: shield + mask BEFORE the agent. Memory (checkpoints) only ever stores the masked message.
    try:
        async with asyncio.timeout(settings.guard_timeout_s + 1):
            g = await guard_input(clients, settings, body.message)
    except (HopError, TimeoutError) as e:
        raise HTTPException(503, detail={"hop": "content_safety", "error": _describe(getattr(e, "cause", e)),
                                         "thread_id": thread_id})
    ev.question_masked = g.text
    ev.guardrails = {"prompt_attack": g.blocked, "redactions": g.redactions}
    if g.blocked:
        span.set_attribute("chat.status", "blocked")
        return _blocked(thread_id, "prompt_shield", g.redactions)

    book, usage = SourceBook(), []
    tools = build_tools(clients, settings, book, thread_id)
    agent_model, final_model = make_models(clients, settings)
    graph = build_graph(agent_model, final_model, tools, book, settings.agent_tool_budget, usage,
                        checkpointer=AsyncPostgresSaver(clients.pg_agent), time_budget_s=settings.agent_time_budget_s,
                        direct_final=settings.agent_direct_final)
    try:
        async with asyncio.timeout(settings.agent_deadline_s):
            state = await graph.ainvoke(
                {"messages": [HumanMessage(g.text)], "tool_calls_used": 0, "final": None},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 4 * settings.agent_tool_budget + 6},
            )
    except TimeoutError:
        raise HTTPException(504, detail={"error": f"deadline {settings.agent_deadline_s:g}s exceeded", "thread_id": thread_id})
    except Exception as e:   # checkpoint store or model failure outside a tool
        if is_content_filter(e):
            # Azure OpenAI's built-in filter (jailbreak / harmful content) refused the prompt. That's a safety
            # outcome, not an outage: measured in the agent eval as a 503 for "Ignore your rules and declare … ".
            span.set_attribute("chat.status", "blocked")
            return _blocked(thread_id, "content_filter", g.redactions, len(usage))
        span.set_attribute("chat.error", type(e).__name__)
        raise HTTPException(503, detail={"hop": "agent", "error": _describe(e), "thread_id": thread_id})
    finally:
        ev.tools = list(book.tools)
        ev.sql = [s["sql"] for s in book.sources.values() if s["kind"] == "data"]
        ev.review_ids = [r["id"] for r in book.review_items]
        ev.guardrails["documents_removed"] = book.removed_values

    final = state["final"]
    ids = dict.fromkeys([*final["source_ids"], *SOURCE_ID.findall(final["answer"])])
    cited = [book.sources[i] for i in ids if i in book.sources]
    ev.sources = [c["id"] for c in cited]
    span.set_attribute("chat.status", final["status"])
    span.set_attribute("chat.tool_calls", state["tool_calls_used"])
    return {
        "thread_id": thread_id, "status": final["status"], "answer": final["answer"], "sources": cited,
        "review_items": [{"id": r["id"], "piid": r["piid"], "rule_id": r["rule_id"], "status": r["status"]}
                         for r in book.review_items],
        "redactions": g.redactions,
        "tool_calls_this_turn": state["tool_calls_used"],
        "usage": {"model_calls": len(usage), "input_tokens": sum(u["input"] for u in usage),
                  "output_tokens": sum(u["output"] for u in usage), "reasoning_tokens": sum(u["reasoning"] for u in usage)},
        "trace_id": _trace_id(),
    }
