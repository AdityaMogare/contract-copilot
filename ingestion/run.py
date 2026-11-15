"""CLI: ingest a FAR snapshot (design 03 §3).

uv run python -m ingestion.run --date 2026-10-28 [--parts 6,15] [--dry-run] [--trace]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date

import httpx

from app.config import get_settings
from ingestion import ecfr
from ingestion.azure_io import AzureIO, to_doc
from ingestion.chunk import chunk_section
from ingestion.parse import parse_part


@dataclass
class Report:
    snapshot: str
    parts: list[str] = field(default_factory=list)
    parts_missing: list[str] = field(default_factory=list)
    parts_failed: dict[str, str] = field(default_factory=dict)   # part → error; run exits 1
    sections: int = 0
    chunks: int = 0
    embedded: int = 0
    skipped_unchanged: int = 0
    deleted_stale: int = 0
    tokens_embedded: int = 0
    max_chunk_tokens: int = 0
    index_created: bool = False
    index_storage_bytes: int | None = None
    seconds: float = 0.0


def plan(chunks, existing: dict[str, str]):
    """Diff new chunks against what's indexed for this part → (to_embed, unchanged_ids, stale_ids)."""
    new_ids = {c.id for c in chunks}
    to_embed = [c for c in chunks if existing.get(c.id) != c.content_hash]
    unchanged = [c.id for c in chunks if existing.get(c.id) == c.content_hash]
    stale = sorted(set(existing) - new_ids)
    return to_embed, unchanged, stale


def ingest_part(part, snapshot, http, io, settings, report: Report, dry_run: bool,
                chunk_opts: dict | None = None) -> None:
    try:
        xml = ecfr.fetch_part_xml(http, snapshot, part)                       # hop 2
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:                                     # reserved / absent part
            report.parts_missing.append(part)
            return
        raise
    amended = ecfr.fetch_amendment_dates(http, snapshot, part)                # hop 1
    sections = parse_part(xml, amended)                                       # hop 4
    salt = f"{settings.embed_deployment}|{settings.embed_dimensions}"
    chunks = [c for s in sections for c in chunk_section(s, hash_salt=salt, **(chunk_opts or {}))]
    report.parts.append(part)
    report.sections += len(sections)
    report.chunks += len(chunks)
    report.max_chunk_tokens = max([report.max_chunk_tokens, *(c.tokens for c in chunks)])
    if dry_run:
        return

    io.put_raw(snapshot, part, xml)                                           # hop 3
    to_embed, unchanged, stale = plan(chunks, io.existing_hashes(part))      # hop 6
    vectors, tokens = io.embed([c.content for c in to_embed]) if to_embed else ([], 0)   # hop 7
    io.write([to_doc(c, v, snapshot) for c, v in zip(to_embed, vectors)], stale)        # hops 8–9
    report.embedded += len(to_embed)
    report.skipped_unchanged += len(unchanged)
    report.deleted_stale += len(stale)
    report.tokens_embedded += tokens
    print(f"part {part}: {len(sections)} sections, {len(chunks)} chunks, "
          f"embedded {len(to_embed)}, unchanged {len(unchanged)}, stale {len(stale)}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, type=date.fromisoformat, help="eCFR snapshot date")
    ap.add_argument("--parts", default=",".join(ecfr.FAR_PARTS))
    ap.add_argument("--dry-run", action="store_true", help="fetch+parse+chunk only; no Azure writes")
    ap.add_argument("--trace", action="store_true", help="log every HTTP request/response (headers, status)")
    ap.add_argument("--index", help="versioned index to write (default: SEARCH_INDEX_VERSION)")
    ap.add_argument("--no-parent-title", action="store_true", help="design 05 E1 off")
    ap.add_argument("--no-definition-units", action="store_true", help="design 05 E2 off")
    args = ap.parse_args(argv)
    if args.trace:
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
        for name in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity", "httpx", "openai"):
            logging.getLogger(name).setLevel(logging.INFO if name != "openai" else logging.DEBUG)

    settings = get_settings()
    if args.index:
        settings = settings.model_copy(update={"search_index_version": args.index})
    chunk_opts = {"parent_title": not args.no_parent_title, "definition_units": not args.no_definition_units}
    report = Report(snapshot=args.date.isoformat())
    started = time.perf_counter()
    io = None
    if not args.dry_run:
        io = AzureIO.build(settings)
        report.index_created = io.ensure_index()                              # hop 5
    with ecfr.make_client() as http:
        for part in args.parts.split(","):
            try:
                ingest_part(part.strip(), args.date, http, io, settings, report, args.dry_run, chunk_opts)
            except Exception as e:  # one bad part must not hide or stop the rest
                report.parts_failed[part.strip()] = f"{type(e).__name__}: {e}"[:500]
                print(f"part {part.strip()}: FAILED {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    if io:
        report.index_storage_bytes = io.storage_bytes()                       # hop 10
    report.seconds = round(time.perf_counter() - started, 1)
    print(json.dumps(asdict(report), indent=2), flush=True)
    return 1 if report.parts_failed else 0


if __name__ == "__main__":
    sys.exit(main())
