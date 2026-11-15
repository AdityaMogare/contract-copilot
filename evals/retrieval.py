"""Retrieval-only eval (design 05): embed + search, no chat. Cheap enough to run every variant.

uv run python -m evals.retrieval --index far-chunks-v1 --mode hybrid --set dev --label v1-hybrid

Metrics over answerable questions: hit@3/5/8/12 (an expected section in the top k) and MRR (1/rank of
the first expected section, 0 if absent from the top 12). `--set heldout` is only for the final
before/after: the held-out set is sealed during tuning (design 05 §2).
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import get_settings
from ingestion.azure_io import AzureIO

ROOT = Path(__file__).parent
SETS = {"dev": "golden.jsonl", "heldout": "heldout.jsonl"}
KS = (3, 5, 8, 12)


def section_of(chunk_id: str) -> str:
    return chunk_id.split("--")[0].replace("_", ".")


def search(client: SearchClient, mode: str, q: str, vector: list[float], k: int, weight: float = 1.0) -> list[str]:
    # weight scales this vector query's contribution to RRF (1.0 = equal to BM25)
    vq = [VectorizedQuery(vector=vector, k_nearest_neighbors=50, fields="content_vector", weight=weight)]
    kwargs = {"bm25": dict(search_text=q), "vector": dict(search_text=None, vector_queries=vq),
              "hybrid": dict(search_text=q, vector_queries=vq)}[mode]
    return [r["id"] for r in client.search(**kwargs, select=["id"], top=k)]


def evaluate(index: str, mode: str, which: str, weight: float = 1.0) -> tuple[dict, list[dict]]:
    settings = get_settings()
    io = AzureIO.build(settings)                    # for embeddings (same deployment + dims as ingest)
    client = SearchClient(str(settings.search_endpoint), index, DefaultAzureCredential())
    items = [json.loads(x) for x in (ROOT / SETS[which]).read_text().splitlines() if x.strip()]
    items = [i for i in items if i["answerable"]]
    vectors, _ = io.embed([i["question"] for i in items])
    rows = []
    for item, vec in zip(items, vectors):
        ranked = [section_of(c) for c in search(client, mode, item["question"], vec, max(KS), weight)]
        exp = set(item["expected_sections"])
        rank = next((n for n, s in enumerate(ranked, 1) if s in exp), None)
        rows.append({"id": item["id"], "rank": rank, "top3": ranked[:3], "expected": sorted(exp)})
    n = len(rows)
    summary = {f"hit@{k}": sum(1 for r in rows if r["rank"] and r["rank"] <= k) for k in KS}
    summary["MRR"] = round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3)
    summary["n"] = n
    return summary, rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--mode", choices=["hybrid", "bm25", "vector"], default="hybrid")
    ap.add_argument("--set", choices=list(SETS), default="dev")
    ap.add_argument("--label", required=True)
    ap.add_argument("--vector-weight", type=float, default=1.0)
    a = ap.parse_args()
    summary, rows = evaluate(a.index, a.mode, a.set, a.vector_weight)
    out = ROOT / "reports" / f"{date.today().isoformat()}-retrieval-{a.set}-{a.label}.md"
    out.parent.mkdir(exist_ok=True)
    lines = [f"# Retrieval eval: {a.label} ({a.set}, {a.index}, {a.mode}, vector weight {a.vector_weight:g})", "",
             "| " + " | ".join(summary) + " |", "|" + "---|" * len(summary),
             "| " + " | ".join(str(v) for v in summary.values()) + " |", "",
             "| id | first-hit rank | expected | top 3 retrieved |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['rank'] or '–'} | {', '.join(r['expected'])} | {', '.join(r['top3'])} |" for r in rows]
    out.write_text("\n".join(lines) + "\n")
    print(json.dumps({"label": a.label, **summary}))
    print("misses (rank > 8 or none):", [(r["id"], r["rank"]) for r in rows if not r["rank"] or r["rank"] > 8])


if __name__ == "__main__":
    main()
