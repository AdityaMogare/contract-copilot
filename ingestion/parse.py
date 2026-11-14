"""eCFR part XML → Sections of text blocks (design 03 §4, "Paragraph labels").

eCFR shape: DIV5 TYPE=PART → [DIV6 TYPE=SUBPART] → DIV8 TYPE=SECTION (HEAD + P/EXTRACT/table…).
We flatten each section into ordered text blocks and mark which blocks start a *top-level*
paragraph ((a), (b), …). That's all the chunker needs to split on regulation structure.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from datetime import date

from defusedxml import ElementTree as ET  # guards against entity-expansion attacks

LABEL = re.compile(r"^\((\w{1,4})\)")
SKIP = {"HEAD", "CITA", "AUTH", "SOURCE"}        # title is kept separately; amendment cites are noise
CONTAINERS = {"EXTRACT", "DIV", "NOTE", "TABLE", "THEAD", "TBODY", "TFOOT"}
LETTERS = string.ascii_lowercase


@dataclass
class Block:
    text: str
    label: str | None = None   # top-level label ("a", "b", …) if this block starts one, else None


@dataclass
class Section:
    number: str                 # "6.302-1"
    title: str                  # "Only one responsible source and no other supplies or services…"
    part: str                   # "6"
    part_title: str             # "Competition Requirements"
    subpart: str | None         # "6.3"
    subpart_title: str | None
    blocks: list[Block] = field(default_factory=list)
    amended_on: date | None = None

    @property
    def url(self) -> str:
        return f"https://www.acquisition.gov/far/{self.number}"


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _flatten(el):
    """Yield leaf text blocks in document order. Tables become one block per row."""
    for child in el:
        tag = child.tag
        if tag in SKIP:
            continue
        if tag == "img":
            yield "[image omitted]"
        elif tag == "TR":
            cells = [_text(c) for c in child]
            if any(cells):
                yield " | ".join(cells)
        elif tag in CONTAINERS:
            yield from _flatten(child)
        else:
            t = _text(child)
            if t:
                yield t


def _strip_heading(head: str, prefix: str) -> str:
    """'PART 6—COMPETITION REQUIREMENTS' → 'Competition Requirements'; '6.302-1 Only one…' → 'Only one…'."""
    title = head.split("—", 1)[1] if "—" in head else head.removeprefix(prefix)
    title = title.strip().rstrip(".")
    return title.title() if title.isupper() else title


def mark_top_level(texts: list[str]) -> list[Block]:
    """Label each block that starts a top-level paragraph.

    FAR nests (a) → (1) → (i) → (A). Only lowercase letters are top-level, but "(i)" is ambiguous:
    roman 1 or the letter after (h). Rule: a letter is top-level iff it's the *expected next* letter.
    "(a)" always (re)starts a sequence: clauses have Alternates that restart at (a).
    """
    blocks, expected = [], "a"
    for t in texts:
        m = LABEL.match(t)
        lab = m.group(1) if m else None
        if lab == "a" or (lab is not None and lab == expected):
            blocks.append(Block(t, lab))
            expected = LETTERS[LETTERS.index(lab) + 1] if lab != "z" else ""
        else:
            blocks.append(Block(t))
    return blocks


def parse_part(xml: bytes | str, amended: dict[str, date] | None = None) -> list[Section]:
    """Parse one eCFR part. `amended` maps section number → amendment date (from the versions API)."""
    root = ET.fromstring(xml)
    part_el = root if root.tag == "DIV5" else root.find(".//DIV5")
    part = part_el.get("N")
    part_title = _strip_heading(part_el.findtext("HEAD", ""), f"PART {part}")
    amended = amended or {}
    sections: list[Section] = []

    def walk(el, subpart=None, subpart_title=None):
        for child in el:
            if child.tag == "DIV6":
                walk(child, child.get("N"), _strip_heading(child.findtext("HEAD", ""), ""))
            elif child.tag == "DIV8":
                head = " ".join(child.findtext("HEAD", "").split())
                if "[Reserved]" in head:
                    continue
                num = child.get("N")
                sections.append(Section(
                    number=num,
                    title=_strip_heading(head, num),
                    part=part, part_title=part_title,
                    subpart=subpart, subpart_title=subpart_title,
                    blocks=mark_top_level(list(_flatten(child))),
                    amended_on=amended.get(num),
                ))

    walk(part_el)
    return sections
