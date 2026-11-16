"""Guardrail eval (design 10): live Content Safety + Language on our AI Services account. No LLM calls.

uv run python -m evals.guardrails_run [--runs 3]

- direct: userPrompt shield → block rate (each attack run --runs times: measured nondeterminism)
- indirect / benign_doc: document shield → detection rate and false flags on real-looking award text
- pii: masked categories vs expected (incl. clause numbers that must NOT be masked)
- false positives: every benign question from the four golden sets through the input guard
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
from app.guardrails import content_safety, pii

HERE = Path(__file__).parent
BENIGN_SETS = ["golden.jsonl", "heldout.jsonl", "sql_golden.jsonl", "agent_golden.jsonl"]


def load(name):
    return [json.loads(l) for l in (HERE / name).read_text().splitlines() if l.strip()]


async def timed(coro):
    t = time.perf_counter()
    out = await coro
    return out, (time.perf_counter() - t) * 1000


async def main(runs: int) -> None:
    s = get_settings().model_copy(update={"guardrails_enabled": True})
    c = build_clients(s)
    items = load("guardrails_golden.jsonl")
    report: dict = {"date": str(date.today()), "runs": runs}
    lat_shield, lat_pii = [], []
    try:
        direct = [i for i in items if i["kind"] == "direct"]
        rows = []
        for i in direct:
            hits = 0
            for _ in range(runs):
                hit, ms = await timed(content_safety.shield_prompt(c, s, i["text"]))
                hits += hit
                lat_shield.append(ms)
            rows.append({"id": i["id"], "detected": f"{hits}/{runs}"})
        report["direct"] = {"blocked_runs": sum(int(r["detected"].split("/")[0]) for r in rows),
                            "total_runs": len(direct) * runs,
                            "always": sum(r["detected"] == f"{runs}/{runs}" for r in rows),
                            "never": [r["id"] for r in rows if r["detected"].startswith("0/")], "items": rows}

        docs = [i for i in items if i["kind"] in ("indirect", "benign_doc")]
        flags = await content_safety.shield_documents(c, s, [i["text"] for i in docs])
        report["indirect"] = {
            "detected": f"{sum(f for i, f in zip(docs, flags) if i['kind'] == 'indirect')}/{sum(i['kind'] == 'indirect' for i in docs)}",
            "missed": [i["id"] for i, f in zip(docs, flags) if i["kind"] == "indirect" and not f],
            "benign_flagged": [i["id"] for i, f in zip(docs, flags) if i["kind"] == "benign_doc" and f]}

        pii_rows = []
        for i in (i for i in items if i["kind"] == "pii"):
            (masked, red), ms = await timed(pii.mask(c, s, i["text"]))
            lat_pii.append(ms)
            got = sorted(r["category"] for r in red)
            pii_rows.append({"id": i["id"], "ok": got == sorted(i["expect"]), "expected": i["expect"], "got": got,
                             "masked": masked})
        report["pii"] = {"correct": f"{sum(r['ok'] for r in pii_rows)}/{len(pii_rows)}", "items": pii_rows}

        benign = [(f, q) for f in BENIGN_SETS for q in load(f) if q.get("kind") != "adversarial"]
        fp, pii_fp = [], []
        for f, q in benign:
            ((attack, ms1), ((masked, red), ms2)) = await asyncio.gather(
                timed(content_safety.shield_prompt(c, s, q["question"])), timed(pii.mask(c, s, q["question"])))
            lat_shield.append(ms1)
            lat_pii.append(ms2)
            if attack:
                fp.append(q["id"])
            if red:
                pii_fp.append({"id": q["id"], "redactions": red, "masked": masked})
        report["false_positives"] = {"benign_questions": len(benign), "shield_blocked": fp, "pii_masked": pii_fp}

        def pct(xs, p):
            return round(statistics.quantiles(xs, n=100)[p - 1])
        report["latency_ms"] = {"shield_p50": round(statistics.median(lat_shield)), "shield_p95": pct(lat_shield, 95),
                                "pii_p50": round(statistics.median(lat_pii)), "pii_p95": pct(lat_pii, 95)}
    finally:
        await close_clients(c)

    out = HERE / "reports" / f"guardrails-{report['date']}.json"
    out.write_text(json.dumps(report, indent=2))
    d, ind, fpos = report["direct"], report["indirect"], report["false_positives"]
    print(f"direct: {d['blocked_runs']}/{d['total_runs']} runs blocked; always {d['always']}/{len(d['items'])}; never {d['never']}")
    print(f"indirect: {ind['detected']} detected, missed {ind['missed']}; benign docs flagged {ind['benign_flagged']}")
    print(f"pii: {report['pii']['correct']} correct; " +
          "; ".join(f"{r['id']} expected {r['expected']} got {r['got']}" for r in report["pii"]["items"] if not r["ok"]))
    print(f"false positives: shield {len(fpos['shield_blocked'])}/{fpos['benign_questions']} {fpos['shield_blocked']}; "
          f"pii masked {len(fpos['pii_masked'])}/{fpos['benign_questions']} {fpos['pii_masked']}")
    print(f"latency: {report['latency_ms']}  → {out.relative_to(HERE.parent)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    asyncio.run(main(ap.parse_args().runs))
