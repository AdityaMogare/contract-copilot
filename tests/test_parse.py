"""Parser tests against real eCFR XML (public domain): Part 6 as fetched for snapshot 2026-10-28,
plus real sections chosen for edge cases (7.103: "(i)" as a letter; 52.203-2: clause in EXTRACT;
2.101: no top-level labels; 1.106: table)."""

from datetime import date
from pathlib import Path

from ingestion.parse import mark_top_level, parse_part

FIX = Path(__file__).parent / "fixtures"


def _part6(**kw):
    return {s.number: s for s in parse_part((FIX / "part-6.xml").read_bytes(), **kw)}


def _edge():
    return {s.number: s for s in parse_part((FIX / "edge-sections.xml").read_bytes())}


def test_part6_hierarchy():
    secs = _part6()
    s = secs["6.302-1"]
    assert s.part == "6" and s.part_title == "Competition Requirements"
    assert s.subpart == "6.3" and s.subpart_title.startswith("Other Than Full and Open Competition")
    assert s.title.startswith("Only one responsible source")
    assert s.url == "https://www.acquisition.gov/far/6.302-1"
    assert secs["6.001"].subpart is None          # sections directly under the part


def test_reserved_sections_skipped():
    secs = _part6()
    assert all("[Reserved]" not in s.title for s in secs.values())


def test_top_level_labels_6_302_1():
    labels = [b.label for b in _part6()["6.302-1"].blocks if b.label]
    assert labels[:4] == ["a", "b", "c", "d"]
    assert "i" not in labels                      # (2)(i) under (a) is roman, not a letter


def test_letter_i_after_h_is_top_level():
    labels = [b.label for b in _edge()["7.103"].blocks if b.label]
    assert labels[7:10] == ["h", "i", "j"]


def test_mark_top_level_rules():
    texts = ["Lead-in.", "(a) A", "(1) one", "(i) roman", "(b) B", "(c) C", "(z) not expected"]
    assert [b.label for b in mark_top_level(texts)] == [None, "a", None, None, "b", "c", None]
    # Clause alternates restart at (a)
    assert [b.label for b in mark_top_level(["(a) x", "(b) y", "Alternate I", "(a) x2"])] == ["a", "b", None, "a"]


def test_clause_text_inside_extract_is_flattened():
    s = _edge()["52.203-2"]
    assert s.blocks[0].text.startswith("As prescribed in 3.103-1")
    assert [b.label for b in s.blocks if b.label][:3] == ["a", "b", "c"]
    assert not any("48 FR 42478" in b.text for b in s.blocks)   # CITA dropped


def test_tables_become_rows():
    rows = [b.text for b in _edge()["1.106"].blocks if " | " in b.text]
    assert rows and rows[0].startswith("FAR segment | OMB control No.")


def test_amendment_dates_attached():
    secs = _part6(amended={"6.302-1": date(2025, 10, 1)})
    assert secs["6.302-1"].amended_on == date(2025, 10, 1)
    assert secs["6.001"].amended_on is None


def test_defined_terms_detected_in_2_101():
    s = _edge()["2.101"]
    terms = [b.term for b in s.blocks if b.term]
    assert len(terms) == 235 and s.is_definition_list
    assert "Agency head" in terms                     # "Agency head or head of the agency means"
    assert "Contingency operation" in terms            # "(10 U.S.C. 101(a)(13)) means"
    assert not _part6()["6.302-1"].is_definition_list


def test_parent_of_subsection():
    s = _part6()["6.302-1"]
    assert (s.parent, s.parent_title) == ("6.302", "Circumstances permitting other than full and open competition")
