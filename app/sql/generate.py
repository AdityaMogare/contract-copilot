"""Hop 2 (design 07): question → SqlDraft with a strict JSON schema. The model is layer 1, never the boundary."""

from __future__ import annotations

from opentelemetry import trace
from pydantic import BaseModel

from app.rag.retrieve import HopError

tracer = trace.get_tracer(__name__)

RULES = """You write ONE PostgreSQL query to answer a question about US Air Force contract awards.

Scope (measured failure modes, follow strictly):
- Every row is a Department of the Air Force contract with at least one action in fiscal year 2025. Never filter
  by agency or office to mean "Air Force"; it's already all Air Force.
- Questions about other agencies (Navy, Army, NASA, …), other fiscal years, grants, or fields not listed below are
  NOT answerable: set answerable=false, sql="", and say why in explanation.
- Group "contractors"/"vendors"/"companies" by recipient_name (one company can have several UEIs).
- Match company names with recipient_name ILIKE '%NAME%' (names are stored in upper case).
- For FAR authority questions use far_authority = 'X' for that exact section, or far_authority LIKE 'X%' to include
  its paragraphs (e.g. 6.302-1(b)(1)); state which in explanation.
- Coded columns: use only the exact VALUES listed for them.
- Money is USD; total_obligated is per award per fiscal year.

SQL rules: a single SELECT (CTEs allowed); only tables awards and transactions; no comments; return at most 100 rows
(add ORDER BY + LIMIT for "top N" questions); give computed columns readable aliases.
explanation: one sentence on what the query counts or sums, in plain English.

Schema:
"""


class SqlDraft(BaseModel):
    answerable: bool
    sql: str
    explanation: str


async def draft(clients, settings, messages: list[dict], usage: dict) -> SqlDraft:
    with tracer.start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.request.model", settings.chat_deployment)
        span.set_attribute("gen_ai.request.reasoning_effort", settings.sql_reasoning_effort)
        try:
            r = await clients.openai_rag.chat.completions.parse(
                model=settings.chat_deployment, messages=messages, response_format=SqlDraft,
                reasoning_effort=settings.sql_reasoning_effort,
                max_completion_tokens=settings.sql_max_completion_tokens,
            )
        except Exception as e:
            raise HopError("chat", e) from e
        u = r.usage
        usage["prompt_tokens"] += u.prompt_tokens
        usage["completion_tokens"] += u.completion_tokens
        usage["reasoning_tokens"] += (u.completion_tokens_details.reasoning_tokens or 0) if u.completion_tokens_details else 0
        span.set_attribute("gen_ai.usage.input_tokens", u.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", u.completion_tokens)
        span.set_attribute("gen_ai.response.finish_reason", r.choices[0].finish_reason)
        parsed = r.choices[0].message.parsed
        if parsed is None:   # length cut-off or refusal: treat as an unusable draft
            return SqlDraft(answerable=False, sql="", explanation="The model did not return a usable query.")
        return parsed


def first_messages(card: str, question: str) -> list[dict]:
    return [{"role": "system", "content": RULES + card}, {"role": "user", "content": question}]


def repair_messages(messages: list[dict], d: SqlDraft, problem: str) -> list[dict]:
    return [*messages, {"role": "assistant", "content": d.model_dump_json()},
            {"role": "user", "content": f"{problem} Fix the query and answer again (same JSON format)."}]
