"""Competition check service (design 08): award lookup → rules → FAR chunks by exact section → review items."""

from __future__ import annotations

from opentelemetry import trace

from app.agent import reviews
from app.agent.rules import RULES_VERSION, THRESHOLD_TEXT, evaluate
from app.rag.retrieve import HopError
from app.sql.execute import run_readonly

tracer = trace.get_tracer(__name__)

AWARD_SQL = """SELECT award_key, piid, parent_idv_piid, award_type, recipient_name, description, fiscal_year,
  total_obligated, current_total_value, potential_total_value, extent_competed_code, extent_competed,
  other_than_full_open, far_authority, solicitation_procedures, number_of_offers_received, type_of_set_aside,
  fair_opportunity_limited_sources, competition_source
FROM awards WHERE piid = %s ORDER BY fiscal_year, award_key LIMIT 10"""


async def find_awards(clients, piid: str) -> list[dict]:
    """PIID is a bound parameter, never formatted into SQL. Read-only as copilot_reader (07 layer 3)."""
    try:
        cols, rows = await run_readonly(clients.pg, AWARD_SQL, 5.0, (piid.strip().upper(),))
    except Exception as e:
        raise HopError("postgres", e) from e
    return [dict(zip(cols, r)) for r in rows]


async def far_chunks(clients, sections: list[str]) -> dict[str, list[dict]]:
    """Exact lookup by section (filter, no search): sections come from rule code, never from the model or user."""
    out: dict[str, list[dict]] = {}
    with tracer.start_as_current_span("far.lookup") as span:
        try:
            for sec in sections:
                res = await clients.docs.search(search_text="*", filter=f"section eq '{sec}'",
                                                select=["id", "citation", "url", "content"], top=20)
                out[sec] = [{"id": r["id"], "citation": r["citation"], "url": r["url"], "content": r["content"]}
                            async for r in res]
        except Exception as e:
            raise HopError("search", e) from e
        span.set_attribute("far.sections", len(sections))
    return out


def threshold_drift(chunks_6304: list[dict]) -> list[str]:
    """The 6.304 tiers are hard-coded in rules.py. If the indexed FAR text stops containing them, say so."""
    text = " ".join(c["content"] for c in chunks_6304)
    return [t for t in THRESHOLD_TEXT if t not in text]


async def run_check(clients, piid: str, thread_id: str | None = None, open_reviews: bool = True) -> dict:
    with tracer.start_as_current_span("competition_check") as span:
        span.set_attribute("check.piid", piid)
        awards = await find_awards(clients, piid)
        if not awards:
            span.set_attribute("check.found", False)
            return {"piid": piid, "found": False, "rules_version": RULES_VERSION, "awards": [], "review_items": []}
        results, all_sections = [], set()
        for a in awards:
            findings = [f.to_dict() for f in evaluate(a)]
            all_sections.update(s for f in findings for s in f["far_sections"])
            results.append({"award": a, "findings": findings})
        chunks = await far_chunks(clients, sorted(all_sections | {"6.304"}))
        drift = threshold_drift(chunks.get("6.304", []))
        for r in results:
            for f in r["findings"]:
                cites = [{"citation": c["citation"], "url": c["url"]} for s in f["far_sections"] for c in chunks.get(s, [])]
                f["far"] = list({c["citation"]: c for c in cites}.values())   # a long paragraph spans 2+ chunks
        items = []
        if open_reviews and clients.pg_agent is not None:
            try:
                for r in results:
                    if r["findings"]:
                        items += await reviews.open_items(clients.pg_agent, r["award"], r["findings"], thread_id)
            except Exception as e:
                raise HopError("postgres", e) from e
        span.set_attribute("check.findings", sum(len(r["findings"]) for r in results))
        return {"piid": piid, "found": True, "rules_version": RULES_VERSION, "threshold_drift": drift,
                "awards": results, "review_items": items, "far_chunks": chunks}
