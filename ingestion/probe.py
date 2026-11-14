"""CLI: hybrid search sanity check (design 03 §3). Same query path feature 04 will use.

uv run python -m ingestion.probe "sole source only one responsible source" [--part 6]
"""

from __future__ import annotations

import argparse
import sys

from azure.search.documents.models import VectorizedQuery

from app.config import get_settings
from ingestion.azure_io import AzureIO


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--part")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args(argv)
    io = AzureIO.build(get_settings())
    vector, _ = io.embed([args.query])          # same deployment AND same dims as ingest
    results = io.search.search(
        search_text=args.query,                                                # BM25 side
        vector_queries=[VectorizedQuery(vector=vector[0], k_nearest_neighbors=50, fields="content_vector")],
        filter=f"part eq '{args.part}'" if args.part else None,
        select=["citation", "section_title"], top=args.top,
    )
    for i, r in enumerate(results, 1):            # @search.score here is the fused RRF score
        print(f"{i}. {r['citation']:<28} {r['@search.score']:.4f}  {r['section_title'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
