"""Human review queue (design 08): items are created by CODE from rule findings; only a signed-in human decides."""

from __future__ import annotations

import json

from opentelemetry import trace

tracer = trace.get_tracer(__name__)
COLUMNS = ("id, created_at, thread_id, award_key, piid, rule_id, statement, human_question, evidence, far_sections, "
           "status, reviewer_oid, decided_at, note")


def _row(r: dict) -> dict:
    return {**r, "created_at": r["created_at"].isoformat(),
            "decided_at": r["decided_at"].isoformat() if r.get("decided_at") else None}


async def open_items(pool, award: dict, findings: list[dict], thread_id: str | None) -> list[dict]:
    """One open item per (award, rule): re-running a check returns the existing open item instead of a duplicate."""
    out = []
    with tracer.start_as_current_span("reviews.open") as span:
        async with pool.connection() as conn:
            for f in findings:
                cur = await conn.execute(
                    f"""INSERT INTO agent.review_items (thread_id, award_key, piid, rule_id, statement, human_question,
                                                        evidence, far_sections)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (award_key, rule_id) WHERE status = 'open' DO NOTHING
                        RETURNING {COLUMNS}""",
                    (thread_id, award["award_key"], award.get("piid"), f["rule_id"], f["statement"], f["human_question"],
                     json.dumps(f["evidence"]), f["far_sections"]))
                row = await cur.fetchone()
                if row is None:   # already open: return that one
                    cur = await conn.execute(f"SELECT {COLUMNS} FROM agent.review_items WHERE award_key = %s "
                                             "AND rule_id = %s AND status = 'open'", (award["award_key"], f["rule_id"]))
                    row = await cur.fetchone()
                out.append(_row(row))
        span.set_attribute("reviews.count", len(out))
    return out


async def list_items(pool, status: str | None, limit: int = 100) -> list[dict]:
    async with pool.connection() as conn:
        if status:
            cur = await conn.execute(f"SELECT {COLUMNS} FROM agent.review_items WHERE status = %s "
                                     "ORDER BY created_at DESC LIMIT %s", (status, limit))
        else:
            cur = await conn.execute(f"SELECT {COLUMNS} FROM agent.review_items ORDER BY created_at DESC LIMIT %s", (limit,))
        return [_row(r) for r in await cur.fetchall()]


async def decide(pool, item_id: int, decision: str, note: str | None, reviewer_oid: str) -> tuple[str, dict | None]:
    """Returns ("ok", item) | ("not_found", None) | ("already_decided", item). Only open items can be decided."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""UPDATE agent.review_items SET status = %s, note = %s, reviewer_oid = %s, decided_at = now()
                WHERE id = %s AND status = 'open' RETURNING {COLUMNS}""", (decision, note, reviewer_oid, item_id))
        row = await cur.fetchone()
        if row:
            return "ok", _row(row)
        cur = await conn.execute(f"SELECT {COLUMNS} FROM agent.review_items WHERE id = %s", (item_id,))
        existing = await cur.fetchone()
        return ("already_decided", _row(existing)) if existing else ("not_found", None)
