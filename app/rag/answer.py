"""Hops 6–8 (design 04): chat with a strict schema → validate → retry once → map citations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel

from app.clients import Clients
from app.config import Settings
from app.rag.prompt import build_messages
from app.rag.retrieve import HopError, RetrievedChunk

tracer = trace.get_tracer(__name__)
Status = Literal["answered", "partial", "not_found"]
NOT_FOUND_TEXT = "I don't know based on the FAR sections I searched."
MARKER = re.compile(r"\[(\d+)\]")


class ModelAnswer(BaseModel):
    """The ONLY thing the model produces (strict JSON schema). Citations are numbers, not strings."""
    status: Status
    answer: str
    sources: list[int]


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    attempts: int = 0


@dataclass
class Result:
    status: Status
    answer: str
    cited: list[RetrievedChunk] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    validation_failed: bool = False


def validate(m: ModelAnswer, k: int) -> str | None:
    """None if OK, else a one-line reason (fed back to the model on the retry)."""
    used = set(m.sources) | {int(x) for x in MARKER.findall(m.answer)}
    bad = sorted(n for n in used if not 1 <= n <= k)
    if bad:
        return f"source numbers {bad} do not exist; only 1..{k} are valid"
    if m.status in ("answered", "partial") and not used:
        return f"status '{m.status}' requires citing at least one source"
    if m.status in ("answered", "partial") and not m.answer.strip():
        return f"status '{m.status}' requires a non-empty answer"
    return None


async def _complete(clients: Clients, settings: Settings, messages: list[dict], usage: Usage) -> ModelAnswer | str:
    """One chat call. Returns the parsed answer, or a reason string if it can't be used."""
    usage.attempts += 1
    with tracer.start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.request.model", settings.chat_deployment)
        span.set_attribute("gen_ai.request.reasoning_effort", settings.rag_reasoning_effort)
        span.set_attribute("rag.attempt", usage.attempts)
        try:
            r = await clients.openai_rag.chat.completions.parse(
                model=settings.chat_deployment, messages=messages, response_format=ModelAnswer,
                reasoning_effort=settings.rag_reasoning_effort,
                max_completion_tokens=settings.rag_max_completion_tokens,
            )
        except Exception as e:
            raise HopError("chat", e) from e
        u = r.usage
        usage.prompt_tokens += u.prompt_tokens
        usage.completion_tokens += u.completion_tokens
        reasoning = (u.completion_tokens_details.reasoning_tokens or 0) if u.completion_tokens_details else 0
        usage.reasoning_tokens += reasoning
        choice = r.choices[0]
        span.set_attribute("gen_ai.usage.input_tokens", u.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", u.completion_tokens)
        span.set_attribute("gen_ai.usage.reasoning_tokens", reasoning)
        span.set_attribute("gen_ai.response.finish_reason", choice.finish_reason)
        if choice.finish_reason == "length":
            return "ran out of completion tokens (reasoning + answer)"
        if choice.message.refusal:
            return f"refused: {choice.message.refusal[:200]}"
        return choice.message.parsed


async def generate(clients: Clients, settings: Settings, question: str, chunks: list[RetrievedChunk]) -> Result:
    if not chunks:   # nothing retrieved → don't pay for an LLM call
        return Result("not_found", NOT_FOUND_TEXT)
    usage = Usage()
    messages = build_messages(question, chunks)
    for attempt in (1, 2):   # validate → retry ONCE → else "I don't know"
        out = await _complete(clients, settings, messages, usage)
        with tracer.start_as_current_span("validate") as span:
            reason = out if isinstance(out, str) else validate(out, len(chunks))
            span.set_attribute("rag.valid", reason is None)
            if reason:
                span.set_attribute("rag.invalid_reason", reason)
        if reason is None:
            break
        if attempt == 1 and not isinstance(out, str):
            messages = [*messages,
                        {"role": "assistant", "content": out.model_dump_json()},
                        {"role": "user", "content": f"That answer is invalid: {reason}. Fix it and answer again."}]
    else:
        return Result("not_found", NOT_FOUND_TEXT, usage=usage, validation_failed=True)

    if out.status == "not_found":
        return Result("not_found", NOT_FOUND_TEXT, usage=usage)
    by_n = {c.n: c for c in chunks}
    order = list(dict.fromkeys([*(int(x) for x in MARKER.findall(out.answer)), *out.sources]))
    return Result(out.status, out.answer, cited=[by_n[n] for n in order], usage=usage)
