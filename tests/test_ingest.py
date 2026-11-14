"""Ingestion orchestration with fakes: no eCFR, no Azure."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from ingestion import ecfr, run
from ingestion.azure_io import IndexingFailed, check_results, index_schema
from ingestion.chunk import chunk_section
from ingestion.parse import parse_part

XML = (Path(__file__).parent / "fixtures" / "part-6.xml").read_bytes()
SNAP = date(2026, 10, 28)
SETTINGS = SimpleNamespace(embed_deployment="embed", embed_dimensions=512)


@dataclass
class FakeIO:
    existing: dict
    written: list = None
    deleted: list = None
    embedded_texts: int = 0

    def put_raw(self, snapshot, part, xml): return f"ecfr/{snapshot}/part-{part}.xml"
    def existing_hashes(self, part): return dict(self.existing)

    def embed(self, texts):
        self.embedded_texts += len(texts)
        return [[0.0] * 512 for _ in texts], 10 * len(texts)

    def write(self, upserts, delete_ids):
        self.written, self.deleted = upserts, delete_ids


@pytest.fixture(autouse=True)
def fake_ecfr(monkeypatch):
    monkeypatch.setattr(ecfr, "fetch_part_xml", lambda http, snap, part: XML)
    monkeypatch.setattr(ecfr, "fetch_amendment_dates", lambda http, snap, part: {})


def _current_chunks():
    salt = "embed|512"
    return [c for s in parse_part(XML) for c in chunk_section(s, hash_salt=salt)]


def _ingest(io):
    rep = run.Report(snapshot=SNAP.isoformat())
    run.ingest_part("6", SNAP, None, io, SETTINGS, rep, dry_run=False)
    return rep


def test_first_run_embeds_everything():
    io = FakeIO(existing={})
    rep = _ingest(io)
    assert rep.embedded == rep.chunks == len(io.written) > 0
    assert io.deleted == []
    doc = next(d for d in io.written if d["id"] == "6_302-1--001")
    assert doc["citation"] == "FAR 6.302-1(b)–(c)" and doc["snapshot_date"].startswith("2026-10-28")


def test_rerun_same_snapshot_embeds_nothing():
    io = FakeIO(existing={c.id: c.content_hash for c in _current_chunks()})
    rep = _ingest(io)
    assert rep.embedded == 0 and io.embedded_texts == 0
    assert rep.skipped_unchanged == rep.chunks


def test_changed_chunk_reembedded_and_stale_deleted():
    existing = {c.id: c.content_hash for c in _current_chunks()}
    existing["6_302-1--001"] = "old-hash"
    existing["6_302-1--003"] = "gone"          # section used to have 4 chunks
    io = FakeIO(existing=existing)
    rep = _ingest(io)
    assert [d["id"] for d in io.written] == ["6_302-1--001"]
    assert io.deleted == ["6_302-1--003"]
    assert rep.deleted_stale == 1


def test_partial_207_failure_raises():
    ok = SimpleNamespace(key="a", succeeded=True, status_code=200, error_message=None)
    bad = SimpleNamespace(key="b", succeeded=False, status_code=400, error_message="bad field")
    check_results([ok])
    with pytest.raises(IndexingFailed, match="1 documents failed"):
        check_results([ok, bad])


def test_schema_vector_field():
    idx = index_schema("far-chunks-v1", 512)
    v = next(f for f in idx.fields if f.name == "content_vector")
    assert v.vector_search_dimensions == 512 and v.hidden is True
    assert next(f for f in idx.fields if f.name == "id").key is True


def test_failed_part_is_reported_and_exit_code_is_1(monkeypatch, capsys):
    def boom(http, snap, part):
        if part == "6":
            raise RuntimeError("search 503")
        return XML
    monkeypatch.setattr(ecfr, "fetch_part_xml", boom)
    monkeypatch.setattr(run, "get_settings", lambda: SETTINGS)
    code = run.main(["--date", "2026-10-28", "--parts", "6,7", "--dry-run"])
    out = capsys.readouterr()
    assert code == 1
    assert '"6": "RuntimeError: search 503"' in out.out
    assert "part 6: FAILED" in out.err
