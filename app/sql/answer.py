"""Orchestration (design 07 §4): draft → validate → execute, with ONE repair attempt."""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg
from opentelemetry import trace

from app.rag.retrieve import HopError
from app.sql import generate, schema_card
from app.sql.execute import run_readonly
from app.sql.validate import MAX_ROWS, validate

tracer = trace.get_tracer(__name__)
# Postgres errors the model can fix (bad column/function/type/grouping/syntax) → repair. Others → hop error.
REPAIRABLE = {"42703", "42883", "42P01", "42601", "42804", "42803", "22P02", "42725", "42P10", "22007", "22008"}


@dataclass
class SqlResult:
    status: str                    # answered | not_answerable | rejected | error
    explanation: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    attempts: int = 0
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0})


async def answer(clients, settings, question: str) -> SqlResult:
    if clients.pg is None:
        raise HopError("postgres", RuntimeError("Postgres not configured"))
    try:
        card = await schema_card.get(clients.pg)
    except Exception as e:
        raise HopError("postgres", e) from e

    res = SqlResult(status="error", explanation="")
    messages = generate.first_messages(card, question)
    for attempt in (1, 2):
        res.attempts = attempt
        d = await generate.draft(clients, settings, messages, res.usage)
        if not d.answerable:
            return _done(res, "not_answerable", d.explanation)

        with tracer.start_as_current_span("validate") as span:
            v = validate(d.sql)
            span.set_attribute("sql.valid", v.ok)
            if not v.ok:
                span.set_attribute("sql.reject_reason", v.reason)
        if not v.ok:
            if attempt == 1:
                messages = generate.repair_messages(messages, d, f"That SQL was rejected by the validator: {v.reason}.")
                continue
            return _done(res, "rejected", f"Generated SQL was rejected twice: {v.reason}", sql=d.sql)

        try:
            columns, rows = await run_readonly(clients.pg, v.exec_sql, settings.sql_timeout_s)
        except psycopg.errors.QueryCanceled:
            return _done(res, "error", f"The query took longer than {settings.sql_timeout_s:g}s and was cancelled.", sql=v.sql)
        except psycopg.Error as e:
            if e.sqlstate in REPAIRABLE and attempt == 1:
                messages = generate.repair_messages(messages, d, f"PostgreSQL error {e.sqlstate}: {str(e).splitlines()[0]}.")
                continue
            if e.sqlstate in REPAIRABLE:
                return _done(res, "error", f"PostgreSQL error {e.sqlstate}: {str(e).splitlines()[0]}", sql=v.sql)
            raise HopError("postgres", e) from e
        except Exception as e:
            raise HopError("postgres", e) from e

        if not rows and attempt == 1:   # measured: both 0-row probe results were wrong filters
            messages = generate.repair_messages(
                messages, d, "The query returned 0 rows. Re-check every filter against the listed VALUES and the scope "
                             "rules; if 0 is genuinely the answer, return the same query.")
            continue
        truncated = v.capped and len(rows) > MAX_ROWS
        return _done(res, "answered", d.explanation, sql=v.sql, columns=columns, rows=rows[:MAX_ROWS], truncated=truncated)
    return res


def _done(res: SqlResult, status: str, explanation: str, **kw) -> SqlResult:
    res.status, res.explanation = status, explanation
    for k, val in kw.items():
        setattr(res, k, val)
    return res
