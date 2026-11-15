from pathlib import Path

from ingestion.chunk import MAX_TOKENS, chunk_section, count_tokens
from ingestion.parse import Block, Section, parse_part

FIX = Path(__file__).parent / "fixtures"
ALL = [s for f in ("part-6.xml", "edge-sections.xml") for s in parse_part((FIX / f).read_bytes())]
BY = {s.number: s for s in ALL}


def _sec(blocks, number="9.999"):
    return Section(number, "Test section", "9", "Test Part", "9.9", "Test Subpart", blocks)


def test_every_chunk_within_token_cap_and_has_header():
    for s in ALL:
        for c in chunk_section(s):
            assert c.tokens <= MAX_TOKENS, (c.id, c.tokens)
            assert c.content.startswith(f"FAR {s.number} {s.title}")
            assert f"\nPart {s.part} " in c.content.split("\n\n", 1)[0]


def test_6_302_1_splits_on_top_level_paragraphs():
    cs = chunk_section(BY["6.302-1"])
    assert [c.citation for c in cs] == ["FAR 6.302-1(a)", "FAR 6.302-1(b)–(c)", "FAR 6.302-1(d)"]
    assert [c.id for c in cs] == ["6_302-1--000", "6_302-1--001", "6_302-1--002"]
    assert "(b) Application." in cs[1].content and "(d)" not in cs[1].content.split("\n\n", 1)[1][:4]


def test_small_section_is_one_chunk_with_lead_in():
    cs = chunk_section(_sec([Block("Lead-in sentence."), Block("(a) Rule.", "a"), Block("(b) Exception.", "b")]))
    assert len(cs) == 1
    assert cs[0].paragraph_range == "(a)–(b)" and "Lead-in sentence." in cs[0].content


def test_oversized_block_is_token_cut():
    big = "word " * 3000
    cs = chunk_section(_sec([Block("(a) " + big, "a")]))
    assert len(cs) > 1 and all(c.tokens <= MAX_TOKENS for c in cs)
    assert all(c.paragraph_range == "(a)" for c in cs)


def test_ids_and_hashes_are_deterministic_and_salted():
    a = chunk_section(BY["6.302-1"], hash_salt="embed|512")
    b = chunk_section(BY["6.302-1"], hash_salt="embed|512")
    c = chunk_section(BY["6.302-1"], hash_salt="embed|1536")
    assert [x.id for x in a] == [x.id for x in b]
    assert [x.content_hash for x in a] == [x.content_hash for x in b]
    assert a[0].content_hash != c[0].content_hash      # changing dims forces a re-embed


def test_no_text_lost():
    for s in ALL:
        joined = "\n".join(c.content.split("\n\n", 1)[1] for c in chunk_section(s))
        for b in s.blocks:
            if count_tokens(b.text) < MAX_TOKENS // 2:
                assert b.text in joined, (s.number, b.text[:60])


def test_range_with_alternate_restart():
    from ingestion.chunk import _range
    assert _range(["b", "c", "d"]) == "(b)–(d)"
    assert _range(["v", "a", "b"]) == "(v); (a)–(b)"
    assert _range(["c", "c"]) == "(c)"          # pieces of one split paragraph
    assert _range([]) == ""


def test_metadata_change_changes_hash():
    from dataclasses import replace
    from datetime import date
    s = BY["6.302-1"]
    a = chunk_section(s)
    b = chunk_section(replace(s, amended_on=date(2030, 1, 1)))
    assert a[0].content == b[0].content and a[0].content_hash != b[0].content_hash


def test_flags_off_reproduce_v1_chunks_exactly():
    """A/B builds must differ only by the experiment: with E1+E2 off, every fixture chunk hashes as in v1."""
    import json
    v1 = json.loads((FIX / "v1-chunk-hashes.json").read_text())
    now = {c.id: c.content_hash for s in ALL
           for c in chunk_section(s, hash_salt="embed|512", parent_title=False, definition_units=False)}
    assert now == v1


def test_parent_title_in_header():
    head = chunk_section(BY["6.302-1"])[0].content.split("\n")[0]
    assert head.endswith("— under 6.302 Circumstances permitting other than full and open competition")
    assert "— under" not in chunk_section(BY["6.001"])[0].content    # not a subsection


def test_one_chunk_per_definition():
    cs = chunk_section(BY["2.101"])
    sat = [c for c in cs if c.citation == 'FAR 2.101 ("Simplified acquisition threshold")']
    assert len(sat) == 1
    assert sat[0].content.split("\n\n", 1)[1].startswith("Simplified acquisition threshold means $350,000")
    assert len(cs) == 236                     # 235 definitions + the section lead-in
    assert all(c.tokens <= MAX_TOKENS for c in cs)
    assert len(chunk_section(BY["6.302-1"])) == 3   # non-definition sections are unaffected
