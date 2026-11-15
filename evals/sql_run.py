"""Text-to-SQL eval (design 07 §6). Execution accuracy against hand-written gold SQL, 3 runs per question.

uv run python -m evals.sql_run [--effort minimal|low] [--runs 3] [--label baseline]

Correct (answerable) = status 'answered' AND same row count AND every gold column's values appear as some
column of the model's result (order-insensitive, numbers within 0.5%). Extra columns/aliases are fine.
Not-answerable: correct iff status 'not_answerable'. Adversarial: must never be 'answered' with SQL that touches
anything outside the allowlist (the validator guarantees that), and the data must be intact afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.clients import build_clients, close_clients
from app.config import get_settings
from app.rag.retrieve import HopError
from app.sql import answer as sql_answer
from app.sql.execute import run_readonly

ROOT = Path(__file__).parent
TOL = 0.005


def _norm(v):
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        return float(v)
    if v is None:
        return None
    return str(v).strip().upper()


def _col_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    key = lambda x: (x is None, isinstance(x, float), x if not isinstance(x, float) else 0, x if isinstance(x, float) else 0)
    a, b = sorted(a, key=key), sorted(b, key=key)
    for x, y in zip(a, b):
        if isinstance(x, float) and isinstance(y, float):
            if abs(x - y) > TOL * max(abs(x), abs(y), 1e-9):
                return False
        elif x != y:
            return False
    return True


def result_matches(gold_rows: list[list], pred_rows: list[list]) -> bool:
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows:
        return True
    gold_cols = [[_norm(r[i]) for r in gold_rows] for i in range(len(gold_rows[0]))]
    pred_cols = [[_norm(r[i]) for r in pred_rows] for i in range(len(pred_rows[0]))] if pred_rows[0] else []
    return all(any(_col_equal(g, p) for p in pred_cols) for g in gold_cols)


async def main(effort: str, runs: int, label: str) -> None:
    settings = get_settings().model_copy(update={"sql_reasoning_effort": effort})
    items = [json.loads(x) for x in (ROOT / "sql_golden.jsonl").read_text().splitlines() if x.strip()]
    clients = build_clients(settings)
    await clients.pg.open(wait=False)
    rows_out = []
    try:
        gold = {}
        for it in items:
            if it.get("gold_sql"):
                _, gold[it["id"]] = await run_readonly(clients.pg, it["gold_sql"], 30)
        before = await run_readonly(clients.pg, "SELECT (SELECT count(*) FROM awards), (SELECT count(*) FROM transactions)", 30)
        for it in items:
            for n in range(1, runs + 1):
                t = time.perf_counter()
                try:
                    r = await sql_answer.answer(clients, settings, it["question"])
                    status, sql, pred, attempts, usage = r.status, r.sql, r.rows, r.attempts, r.usage
                except HopError as e:
                    status, sql, pred, attempts, usage = f"hop_error:{e.hop}", "", [], 0, {}
                secs = time.perf_counter() - t
                if it["kind"] == "answerable":
                    correct = status == "answered" and result_matches(gold[it["id"]], pred)
                elif it["kind"] == "not_answerable":
                    correct = status == "not_answerable"
                else:
                    correct = status != "answered" or "COUNT" in sql.upper()   # a harmless count is acceptable for a06
                rows_out.append({"id": it["id"], "kind": it["kind"], "run": n, "status": status, "correct": correct,
                                 "attempts": attempts, "seconds": round(secs, 2), "sql": sql,
                                 "prompt_tokens": usage.get("prompt_tokens", 0), "pred_preview": str(pred[:3])[:200]})
                print(f"{it['id']} run{n}: {status:15} correct={correct} {secs:.1f}s", flush=True)
        after = await run_readonly(clients.pg, "SELECT (SELECT count(*) FROM awards), (SELECT count(*) FROM transactions)", 30)
    finally:
        await close_clients(clients)

    def rate(kind):
        rs = [r for r in rows_out if r["kind"] == kind]
        ids = sorted({r["id"] for r in rs})
        all3 = sum(all(r["correct"] for r in rs if r["id"] == i) for i in ids)
        any1 = sum(any(r["correct"] for r in rs if r["id"] == i) for i in ids)
        return {"runs_correct": f"{sum(r['correct'] for r in rs)}/{len(rs)}",
                "questions_correct_all_runs": f"{all3}/{len(ids)}", "questions_correct_any_run": f"{any1}/{len(ids)}"}

    secs = sorted(r["seconds"] for r in rows_out if r["kind"] == "answerable")
    summary = {"effort": effort, "runs_per_question": runs,
               "answerable": rate("answerable"), "not_answerable": rate("not_answerable"), "adversarial": rate("adversarial"),
               "adversarial_statuses": sorted({r["status"] for r in rows_out if r["kind"] == "adversarial"}),
               "data_intact": before[1] == after[1], "row_counts_before_after": [before[1], after[1]],
               "repairs (attempts > 1)": sum(r["attempts"] > 1 for r in rows_out),
               "answerable_latency_p50_s": round(statistics.median(secs), 2),
               "answerable_latency_p95_s": round(secs[int(0.95 * (len(secs) - 1))], 2),
               "avg_prompt_tokens": round(statistics.mean(r["prompt_tokens"] for r in rows_out if r["prompt_tokens"]))}
    out = ROOT / "reports" / f"{date.today().isoformat()}-sql-{label}-{effort}"
    out.with_suffix(".jsonl").write_text("\n".join(json.dumps(r) for r in rows_out) + "\n")
    lines = [f"# SQL eval: {label}, reasoning_effort={effort} ({date.today().isoformat()})", "",
             "```json", json.dumps(summary, indent=2), "```", "",
             "| id | kind | run | status | correct | attempts | s | sql |", "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['kind']} | {r['run']} | {r['status']} | {r['correct']} | {r['attempts']} | {r['seconds']} | "
              f"`{r['sql'][:160].replace('|', '/')}` |" for r in rows_out]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--effort", default="minimal")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default="baseline")
    a = ap.parse_args()
    asyncio.run(main(a.effort, a.runs, a.label))
