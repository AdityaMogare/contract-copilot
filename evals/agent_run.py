"""Agent eval (design 08 §6). Runs POST /chat in-process; records every tool call via a wrapper.

uv run python -m evals.agent_run [--effort minimal|low] [--runs 2] [--label baseline]
Scoring is fixed here before any run (see design 08 and the golden file's fields).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).parent
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
VERDICT = re.compile(r"\b(is|are|was|were)\s+(illegal|unlawful|non-?compliant|in violation)\b|\bviolat(es|ed|ing)\s+(the\s+)?(law|FAR)\b"
                     r"|\b(yes|no)[,.]?\s+(boeing|it|they)\s+(is|are)\b", re.I)


def numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in NUM.findall(text)]


def has_gold(text: str, gold: float) -> bool:
    return any(abs(x - gold) <= 0.005 * max(abs(gold), 1) for x in numbers(text))


def score(item: dict, b: dict, calls: list[dict]) -> dict:
    names = {c["name"] for c in calls}
    cited_secs = {s["citation"].split()[1].split("(")[0] for s in b.get("sources", []) if s.get("kind") == "regulation"}
    rules = sorted({s["rule_id"] for s in b.get("sources", []) if s.get("kind") == "check"})
    invented = [c["args"].get("piid") for c in calls if c["name"] == "competition_check" and c["invented"]]
    verdict = bool(VERDICT.search(b.get("answer", "")))
    k, ok = item["kind"], False
    routed = set(item.get("tools", [])) <= names
    if k == "far":
        ok = b["status"] == "answered" and routed and set(item["sections"]) <= cited_secs
    elif k == "data":
        ok = b["status"] == "answered" and routed and (
            has_gold(b["answer"], item["gold"]) if "gold" in item else item["gold_text"] in b["answer"].upper())
    elif k == "combined":
        ok = b["status"] == "answered" and routed and has_gold(b["answer"], item["gold"]) and set(item["sections"]) <= cited_secs
    elif k == "check":
        ok = routed and rules == sorted(item["rules"]) and not verdict
    elif k == "oos":
        ok = b["status"] == "not_found"
    elif k == "adversarial":
        ok = not invented and not verdict
    return {"correct": ok, "routed": routed, "tools": sorted(names), "cited_sections": sorted(cited_secs),
            "rules": rules, "invented_piids": invented, "verdict_language": verdict}


def main(effort: str, runs: int, label: str) -> None:
    import app.routers.chat as chat_router
    from app.config import get_settings
    from app.main import app

    get_settings.cache_clear()
    settings = get_settings()
    object.__setattr__(settings, "agent_reasoning_effort", effort)
    recorded: list[dict] = []
    original = chat_router.build_tools

    def recording_build_tools(*a, **k):
        tools = original(*a, **k)
        for t in tools:
            f = t.coroutine

            async def wrapped(*args, _f=f, _n=t.name, **kw):
                out = await _f(*args, **kw)
                recorded.append({"name": _n, "args": kw, "invented": _n == "competition_check" and (
                    str(out).startswith("No FY2025") or "not a valid PIID" in str(out))})
                return out
            t.coroutine = wrapped
        return tools

    chat_router.build_tools = recording_build_tools
    items = [json.loads(x) for x in (ROOT / "agent_golden.jsonl").read_text().splitlines() if x.strip()]
    rows = []
    with TestClient(app) as c:
        for it in items:
            for n in range(1, runs + 1):
                recorded.clear()
                t = time.perf_counter()
                r = c.post("/chat", json={"message": it["question"]})
                secs = time.perf_counter() - t
                b = r.json() if r.status_code == 200 else {"status": f"http_{r.status_code}", "answer": "", "sources": []}
                s = score(it, b, list(recorded))
                rows.append({"id": it["id"], "kind": it["kind"], "run": n, "status": b["status"], "seconds": round(secs, 1),
                             "tool_calls": len(recorded), "usage": b.get("usage"), "answer": b.get("answer", "")[:600], **s})
                print(f"{it['id']} run{n} {it['kind']:11} {b['status']:10} correct={s['correct']} tools={s['tools']} {secs:.1f}s", flush=True)

    def rate(kinds):
        rs = [r for r in rows if r["kind"] in kinds]
        return f"{sum(r['correct'] for r in rs)}/{len(rs)}"
    secs = sorted(r["seconds"] for r in rows)
    summary = {
        "effort": effort, "runs_per_question": runs,
        "far": rate({"far"}), "data": rate({"data"}), "combined": rate({"combined"}), "check": rate({"check"}),
        "out_of_scope": rate({"oos"}), "adversarial": rate({"adversarial"}), "overall": rate({r["kind"] for r in rows}),
        "routing_correct": f"{sum(r['routed'] for r in rows if r['kind'] in ('far','data','combined','check'))}/"
                           f"{sum(1 for r in rows if r['kind'] in ('far','data','combined','check'))}",
        "invented_piid_calls": sum(len(r["invented_piids"]) for r in rows),
        "verdict_language": sum(r["verdict_language"] for r in rows),
        "http_errors": sum(1 for r in rows if r["status"].startswith("http_")),
        "latency_p50_s": statistics.median(secs), "latency_p95_s": secs[int(0.95 * (len(secs) - 1))],
        "avg_tool_calls": round(statistics.mean(r["tool_calls"] for r in rows), 2),
        "avg_model_calls": round(statistics.mean((r["usage"] or {}).get("model_calls", 0) for r in rows), 2),
        "avg_input_tokens": round(statistics.mean((r["usage"] or {}).get("input_tokens", 0) for r in rows)),
    }
    out = ROOT / "reports" / f"{date.today().isoformat()}-agent-{label}-{effort}"
    out.with_suffix(".jsonl").write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n")
    lines = [f"# Agent eval: {label}, agent reasoning_effort={effort} ({date.today().isoformat()})", "", "```json",
             json.dumps(summary, indent=2), "```", "", "| id | kind | run | status | correct | tools | s | answer |",
             "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['kind']} | {r['run']} | {r['status']} | {r['correct']} | {','.join(r['tools'])} | "
              f"{r['seconds']} | {r['answer'][:140].replace('|', '/').replace(chr(10), ' ')} |" for r in rows]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--effort", default="minimal")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--label", default="baseline")
    a = ap.parse_args()
    main(a.effort, a.runs, a.label)
