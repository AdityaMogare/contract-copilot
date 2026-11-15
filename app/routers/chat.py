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
from app.config import Settings, get_settings
from app.routers.ask import _trace_id
from app.routers.smoke import _describe

router = APIRouter()


def is_content_filter(e: BaseException) -> bool:
    """Azure OpenAI rejects filtered prompts with HTTP 400, code 'content_filter'."""
    return getattr(e, "code", None) == "content_filter" or "content_filter" in str(e)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: uuid.UUID | None = None


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, settings: Settings = Depends(get_settings)):
    clients = request.app.state.clients
    if clients.pg_agent is None:
        raise HTTPException(503, detail={"hop": "postgres", "error": "memory store (Postgres) not configured"})
    thread_id = str(body.thread_id or uuid.uuid4())
    book, usage = SourceBook(), []
    tools = build_tools(clients, settings, book, thread_id)
    agent_model, final_model = make_models(clients, settings)
    graph = build_graph(agent_model, final_model, tools, book, settings.agent_tool_budget, usage,
                        checkpointer=AsyncPostgresSaver(clients.pg_agent), time_budget_s=settings.agent_time_budget_s)
    span = trace.get_current_span()
    span.set_attribute("chat.thread_id", thread_id)
    try:
        async with asyncio.timeout(settings.agent_deadline_s):
            state = await graph.ainvoke(
                {"messages": [HumanMessage(body.message)], "tool_calls_used": 0, "final": None},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 4 * settings.agent_tool_budget + 6},
            )
    except TimeoutError:
        raise HTTPException(504, detail={"error": f"deadline {settings.agent_deadline_s:g}s exceeded", "thread_id": thread_id})
    except Exception as e:   # checkpoint store or model failure outside a tool
        if is_content_filter(e):
            # Azure OpenAI's built-in filter (jailbreak / harmful content) refused the prompt. That's a safety
            # outcome, not an outage: measured in the agent eval as a 503 for "Ignore your rules and declare … ".
            span.set_attribute("chat.status", "blocked")
            return {"thread_id": thread_id, "status": "blocked", "sources": [], "review_items": [],
                    "answer": "I can't help with that request: it was blocked by the content safety filter. "
                              "Ask about the FAR or the award data and I'll cite what I find.",
                    "tool_calls_this_turn": 0, "usage": {"model_calls": len(usage)}, "trace_id": _trace_id()}
        span.set_attribute("chat.error", type(e).__name__)
        raise HTTPException(503, detail={"hop": "agent", "error": _describe(e), "thread_id": thread_id})

    final = state["final"]
    ids = dict.fromkeys([*final["source_ids"], *SOURCE_ID.findall(final["answer"])])
    cited = [book.sources[i] for i in ids if i in book.sources]
    span.set_attribute("chat.status", final["status"])
    span.set_attribute("chat.tool_calls", state["tool_calls_used"])
    return {
        "thread_id": thread_id, "status": final["status"], "answer": final["answer"], "sources": cited,
        "review_items": [{"id": r["id"], "piid": r["piid"], "rule_id": r["rule_id"], "status": r["status"]}
                         for r in book.review_items],
        "tool_calls_this_turn": state["tool_calls_used"],
        "usage": {"model_calls": len(usage), "input_tokens": sum(u["input"] for u in usage),
                  "output_tokens": sum(u["output"] for u in usage), "reasoning_tokens": sum(u["reasoning"] for u in usage)},
        "trace_id": _trace_id(),
    }
