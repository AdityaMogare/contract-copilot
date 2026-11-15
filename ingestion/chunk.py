"""Section → Chunks, clause-aware (design 03 §4 Decisions).

Rules, in order:
1. A chunk never crosses a section boundary.
2. Units = top-level paragraphs ((a), (b), …). A lead-in before (a) joins the first unit.
3. Greedily pack whole units into chunks of ≤ MAX_TOKENS (header included).
4. Only a unit too big on its own is split, at block boundaries, and only a single block too big
   on its own is cut by tokens (last resort; e.g. huge definitions in 2.101).
5. Every chunk starts with a contextual header so it stands alone for BM25 and the embedding.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

import tiktoken

from ingestion.parse import Section

MAX_TOKENS = 700
_enc = tiktoken.get_encoding("cl100k_base")    # the tokenizer text-embedding-3-* uses


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


@dataclass
class Chunk:
    id: str
    section: str
    part: str
    subpart: str | None
    section_title: str
    paragraph_range: str
    citation: str
    url: str
    content: str
    content_hash: str
    amended_on: date | None
    tokens: int


@dataclass
class _Piece:
    texts: list[str]
    labels: list[str]
    tokens: int
    term: str | None = None


TERM_SLACK = 40   # header tokens reserved for a defined term (E2)


def header(s: Section, parent_title: bool = False, term: str | None = None) -> str:
    h = f"FAR {s.number} {s.title}"
    if parent_title and s.parent_title:                 # E1: "16.202-2 Application" alone says nothing
        h += f" — under {s.parent} {s.parent_title}"
    if term:                                            # E2: the term is the strongest signal
        h += f' — "{term}"'
    h += f"\nPart {s.part} {s.part_title}"
    if s.subpart:
        h += f" > Subpart {s.subpart} {s.subpart_title}"
    return h


def _units(s: Section) -> list[_Piece]:
    units: list[_Piece] = []
    for b in s.blocks:
        if b.label is not None and units and units[-1].labels:
            units.append(_Piece([b.text], [b.label], 0))
        elif b.label is not None and units:          # first label: the lead-in joins it
            units[-1].texts.append(b.text)
            units[-1].labels.append(b.label)
        elif not units:
            units.append(_Piece([b.text], [b.label] if b.label else [], 0))
        else:
            units[-1].texts.append(b.text)
    for u in units:
        u.tokens = count_tokens("\n".join(u.texts))
    return units


def _definition_units(s: Section) -> list[_Piece]:
    """One unit per defined term. Text before the first term (the section's lead-in) is its own unit."""
    units: list[_Piece] = []
    for b in s.blocks:
        if b.term or not units:
            units.append(_Piece([b.text], [b.label] if b.label else [], 0, b.term))
        else:
            units[-1].texts.append(b.text)
    for u in units:
        u.tokens = count_tokens("\n".join(u.texts))
    return units


def _hard_split(text: str, budget: int) -> list[str]:
    toks = _enc.encode(text)
    return [_enc.decode(toks[i:i + budget]) for i in range(0, len(toks), budget)]


def _fit(units: list[_Piece], budget: int) -> list[_Piece]:
    """Break any unit larger than the budget into block-sized (or token-cut) pieces."""
    out: list[_Piece] = []
    for u in units:
        if u.tokens <= budget:
            out.append(u)
            continue
        for t in u.texts:
            parts = [t] if count_tokens(t) <= budget else _hard_split(t, budget)
            out += [_Piece([p], list(u.labels), count_tokens(p), u.term) for p in parts]
    return out


def _range(labels: list[str]) -> str:
    """Labels → "(b)–(d)". A restart at (a) (a clause Alternate) starts a new run: "(v); (a)–(c)"."""
    runs: list[list[str]] = []
    for lab in labels:
        if not runs or (lab == "a" and runs[-1][-1] != "a"):
            runs.append([lab])
        elif lab != runs[-1][-1]:
            runs[-1].append(lab)
    return "; ".join(f"({r[0]})" if len(r) == 1 else f"({r[0]})–({r[-1]})" for r in runs)


def chunk_section(s: Section, hash_salt: str = "", parent_title: bool = True,
                  definition_units: bool = True) -> list[Chunk]:
    """Flags exist for A/B index builds (design 05). Both False reproduces the v1 chunks exactly."""
    defs = definition_units and s.is_definition_list
    base = header(s, parent_title)
    budget = MAX_TOKENS - count_tokens(base) - 4 - (TERM_SLACK if defs else 0)   # 4: blank line + joins
    groups: list[list[_Piece]] = [[]]
    used = 0
    for p in _fit(_definition_units(s) if defs else _units(s), budget):
        # Definitions are never packed together: one term per vector is the point of E2.
        if groups[-1] and (defs or used + p.tokens + 1 > budget):
            groups.append([])
            used = 0
        groups[-1].append(p)
        used += p.tokens + 1

    chunks = []
    for i, g in enumerate(x for x in groups if x):
        term = g[0].term if defs else None
        head = header(s, parent_title, term)
        body = "\n".join(t for p in g for t in p.texts)
        content = f"{head}\n\n{body}"
        rng = _range([lab for p in g for lab in p.labels])
        citation = f"FAR {s.number}{rng}" + (f' ("{term}")' if term else "")
        # Hash everything we write except the vector, so a metadata-only fix (e.g. a citation)
        # still counts as "changed" and reaches the index.
        meta = f"{rng}|{s.title}|{s.subpart}|{s.amended_on}"
        if term:
            meta += f"|{term}"
        chunks.append(Chunk(
            id=f"{s.number.replace('.', '_')}--{i:03d}",
            section=s.number, part=s.part, subpart=s.subpart, section_title=s.title,
            paragraph_range=rng, citation=citation, url=s.url,
            content=content,
            content_hash=hashlib.sha256(f"{hash_salt}\n{meta}\n{content}".encode()).hexdigest(),
            amended_on=s.amended_on, tokens=count_tokens(content),
        ))
    return chunks
