"""Score the RAG pipeline on the golden set (design 04 §6). Reports only what it measures.

uv run python -m evals.run [--label baseline]

Runs the same hops as POST /ask (embed → hybrid search → generate) in-process, so it can score
retrieval too (the API doesn't return the chunks it didn't cite). Sequential on purpose: `chat` is
50K TPM and each question is ~4K tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import date
from pathlib import Path

from app.clients import build_clients, close_clients
from app.config import get_settings
from app.rag.answer import generate
from app.rag.retrieve import HopError, embed_query, hybrid_search

ROOT = Path(__file__).parent


def section_of(chunk_id: str) -> str:
    return chunk_id.split("--")[0].replace("_", ".")      # "52_219-14--001" → "52.219-14"


async def run_one(clients, settings, item: dict) -> dict:
    t = time.perf_counter()
    try:
        vec = await embed_query(clients, settings, item["question"])
        chunks = await hybrid_search(clients, settings, item["question"], vec, None)
        res = await generate(clients, settings, item["question"], chunks)
    except HopError as e:
        return {**item, "error": f"{e.hop}: {type(e.cause).__name__}", "seconds": time.perf_counter() - t}
    retrieved = [section_of(c.id) for c in chunks]
    cited = [section_of(c.id) for c in res.cited]
    exp = set(item["expected_sections"])
    return {
        **item,
        "status": res.status,
        "seconds": round(time.perf_counter() - t, 2),
        "retrieved_sections": retrieved,
        "cited_sections": cited,
        "retrieval_hit": bool(exp & set(retrieved)) if exp else None,
        "citation_hit": bool(exp & set(cited)) if exp else None,
        "validation_failed": res.validation_failed,
        "attempts": res.usage.attempts,
        "prompt_tokens": res.usage.prompt_tokens,
        "completion_tokens": res.usage.completion_tokens,
        "reasoning_tokens": res.usage.reasoning_tokens,
        "answer": res.answer,
    }


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    ans = [r for r in ok if r["answerable"]]
    una = [r for r in ok if not r["answerable"]]
    secs = sorted(r["seconds"] for r in ok)
    return {
        "questions": len(rows),
        "errors": len(rows) - len(ok),
        "retrieval_hit@k (answerable)": pct(sum(r["retrieval_hit"] for r in ans), len(ans)),
        "answered_or_partial (answerable)": pct(sum(r["status"] != "not_found" for r in ans), len(ans)),
        "fully_answered (answerable)": pct(sum(r["status"] == "answered" for r in ans), len(ans)),
        "citation_hit (answerable, any expected section cited)": pct(sum(r["citation_hit"] for r in ans), len(ans)),
        "false_idk (answerable → not_found)": pct(sum(r["status"] == "not_found" for r in ans), len(ans)),
        "correct_idk (unanswerable → not_found)": pct(sum(r["status"] == "not_found" for r in una), len(una)),
        "validation_failed": sum(r["validation_failed"] for r in ok),
        "retries (attempts > 1)": sum(r["attempts"] > 1 for r in ok),
        "latency_p50_s": round(statistics.median(secs), 2) if secs else None,
        "latency_p95_s": round(secs[min(len(secs) - 1, int(0.95 * len(secs)))], 2) if secs else None,
        "avg_prompt_tokens": round(statistics.mean(r["prompt_tokens"] for r in ok)) if ok else None,
        "avg_completion_tokens (incl. reasoning)": round(statistics.mean(r["completion_tokens"] for r in ok)) if ok else None,
    }


def write_report(label: str, settings, rows: list[dict], summary: dict) -> Path:
    out = ROOT / "reports" / f"{date.today().isoformat()}-{label}"
    out.parent.mkdir(exist_ok=True)
    (out.with_suffix(".jsonl")).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    lines = [f"# Eval: {label} ({date.today().isoformat()})", "",
             f"Config: index alias `{settings.search_index}`, top_k={settings.rag_top_k}, "
             f"reasoning_effort={settings.rag_reasoning_effort}, chat=`{settings.chat_deployment}`, "
             f"embed dims={settings.embed_dimensions}. Golden set: `evals/golden.jsonl`.", "",
             "| Metric | Value |", "|---|---|", *[f"| {k} | {v} |" for k, v in summary.items()], "",
             "| id | answerable | status | retrieval hit | citation hit | s | expected | cited |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['id']} | {r['answerable']} | ERROR {r['error']} | | | | | |")
            continue
        lines.append(f"| {r['id']} | {r['answerable']} | {r['status']} | {r['retrieval_hit']} | {r['citation_hit']} | "
                     f"{r['seconds']} | {', '.join(r['expected_sections'])} | {', '.join(dict.fromkeys(r['cited_sections']))} |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    return out.with_suffix(".md")


async def main(label: str) -> None:
    settings = get_settings()
    items = [json.loads(line) for line in (ROOT / "golden.jsonl").read_text().splitlines() if line.strip()]
    clients = build_clients(settings)
    rows = []
    try:
        for item in items:
            r = await run_one(clients, settings, item)
            rows.append(r)
            print(f"{r['id']}: {r.get('status', r.get('error'))} ({r['seconds']:.1f}s)", flush=True)
    finally:
        await close_clients(clients)
    summary = summarize(rows)
    path = write_report(label, settings, rows, summary)
    print(json.dumps(summary, indent=2))
    print(f"report: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="baseline")
    asyncio.run(main(ap.parse_args().label))
