"""Agent tools (design 08 §6). Each wraps existing, already-evaluated code (04 retrieval, 07 Text-to-SQL, the 08
rules) and registers every piece of evidence in a per-turn SourceBook, so the final answer can only cite ids a
tool actually returned this turn: R* = FAR text, D* = executed SQL result, C* = competition-check finding."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from langchain_core.tools import StructuredTool
from opentelemetry import trace

from app.agent.check import run_check
from app.guardrails.check import shield_rows
from app.rag.retrieve import embed_query, hybrid_search
from app.sql.answer import answer as sql_answer

tracer = trace.get_tracer(__name__)
PIID_RE = re.compile(r"^[A-Z0-9-]{4,60}$")
SEARCH_TOP_K = 6


@dataclass
class SourceBook:
    sources: dict[str, dict] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=lambda: {"R": 0, "D": 0, "C": 0})
    review_items: list[dict] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)        # names called this turn (audit log)
    removed_values: int = 0                              # third-party values withheld by the document shield

    def add(self, kind: str, payload: dict) -> str:
        if kind == "R":   # the same FAR chunk returned twice keeps one id
            for sid, s in self.sources.items():
                if s.get("chunk_id") == payload.get("chunk_id"):
                    return sid
        self.counters[kind] += 1
        sid = f"{kind}{self.counters[kind]}"
        self.sources[sid] = {"id": sid, **payload}
        return sid


def build_tools(clients, settings, book: SourceBook, thread_id: str | None) -> list[StructuredTool]:

    async def search_regulations(query: str) -> str:
        """Search the Federal Acquisition Regulation (FAR) text. Use for what the rules say: requirements,
        thresholds, definitions, exceptions, procedures. Returns numbered FAR excerpts [R#] with citations."""
        book.tools.append("search_regulations")
        with tracer.start_as_current_span("tool.search_regulations"):
            vec = await embed_query(clients, settings, query)
            chunks = await hybrid_search(clients, settings, query, vec, None)
            out = []
            for c in chunks[:SEARCH_TOP_K]:
                sid = book.add("R", {"kind": "regulation", "chunk_id": c.id, "citation": c.citation, "url": c.url})
                out.append(f"[{sid}] {c.citation}\n{c.content}")
            return "\n\n".join(out) or "No FAR text found."

    async def query_contracts(question: str) -> str:
        """Answer a question about FY2025 US Air Force contract award DATA (counts, sums, top contractors,
        competition coding, offers) with validated read-only SQL. Not for regulation text. Returns [D#]."""
        book.tools.append("query_contracts")
        with tracer.start_as_current_span("tool.query_contracts"):
            r = await sql_answer(clients, settings, question)
            if r.status != "answered":
                return f"query_contracts status={r.status}: {r.explanation}"
            # Design 10: award text (descriptions, recipient names) is third-party data the model is about to read.
            # Shield it as documents first; if the shield can't run this raises, and the model sees an error, not rows.
            rows, removed = await shield_rows(clients, settings, r.rows[:20])
            book.removed_values += removed
            sid = book.add("D", {"kind": "data", "sql": r.sql, "columns": r.columns, "rows": rows,
                                 "row_count": len(r.rows), "truncated": r.truncated, "explanation": r.explanation})
            out = {"id": sid, "explanation": r.explanation, "columns": r.columns,
                   "rows": rows, "row_count": len(r.rows), "truncated": r.truncated}
            if removed:
                out["note"] = (f"{removed} value(s) were removed because the content shield flagged them as possible "
                               "prompt injection. Say so; do not guess what they contained.")
            return json.dumps(out, default=str)

    async def competition_check(piid: str) -> str:
        """Run the FAR Part 6 competition check for ONE award identified by its PIID (contract number). Only use a
        PIID the user gave or that query_contracts returned; never guess one. Returns findings [C#] for HUMAN review
        with FAR excerpts [R#]. Findings are questions to verify, never legal conclusions."""
        book.tools.append("competition_check")
        with tracer.start_as_current_span("tool.competition_check") as span:
            p = piid.strip().upper()
            if not PIID_RE.match(p):
                return f"'{piid}' is not a valid PIID format. Do not guess PIIDs."
            r = await run_check(clients, p, thread_id=thread_id)
            span.set_attribute("check.found", r["found"])
            if not r["found"]:   # measured: the model invents PIIDs; never open review items for them
                return f"No FY2025 Air Force award with PIID {p} exists in the data. Do not guess PIIDs."
            book.review_items += r["review_items"]
            far_ids, texts = {}, {}
            for sec, chunks in r["far_chunks"].items():
                far_ids[sec] = []
                for c in chunks:
                    sid = book.add("R", {"kind": "regulation", "chunk_id": c["id"], "citation": c["citation"], "url": c["url"]})
                    far_ids[sec].append(sid)
                    texts[sid] = c["content"]
            lines = []
            for a in r["awards"]:
                aw = a["award"]
                lines.append(f"Award {aw['piid']} ({aw['recipient_name']}), extent competed: {aw['extent_competed']}, "
                             f"FAR authority: {aw['far_authority']}, offers: {aw['number_of_offers_received']}, "
                             f"potential value: {aw['potential_total_value']}")
                if not a["findings"]:
                    lines.append("No findings: nothing in the recorded data triggers a v1 rule.")
                for f in a["findings"]:
                    cid = book.add("C", {"kind": "check", "piid": aw["piid"], "rule_id": f["rule_id"],
                                         "statement": f["statement"], "human_question": f["human_question"],
                                         "far": f["far"]})
                    refs = [i for s in f["far_sections"] for i in far_ids.get(s, [])]
                    lines.append(f"[{cid}] {f['rule_id']}: {f['statement']} Human reviewer must verify: "
                                 f"{f['human_question']} (FAR: {', '.join(refs)})")
            excerpts = [f"[{sid}] {book.sources[sid]['citation']}\n{text}" for sid, text in texts.items()]
            return "\n".join(lines) + "\n\nFAR excerpts:\n" + "\n\n".join(excerpts)

    return [StructuredTool.from_function(coroutine=f, name=f.__name__, description=f.__doc__)
            for f in (search_regulations, query_contracts, competition_check)]
