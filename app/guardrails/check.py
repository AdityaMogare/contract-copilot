"""Input guard used by every endpoint before any LLM call (design 10 §1)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.guardrails import content_safety, pii

REMOVED = "[removed: flagged by prompt shield]"


@dataclass
class InputGuard:
    text: str                                  # masked text: the only version the LLM, memory and audit see
    blocked: bool = False
    redactions: list[dict] = field(default_factory=list)


async def guard_input(clients, settings, text: str) -> InputGuard:
    """Shield + PII in parallel. Raises HopError("content_safety") if either can't run (fail closed)."""
    if not settings.guardrails_enabled:
        return InputGuard(text=text)
    attack, (masked, redactions) = await asyncio.gather(
        content_safety.shield_prompt(clients, settings, text), pii.mask(clients, settings, text))
    return InputGuard(text=masked, blocked=attack, redactions=redactions)


MIN_SHIELD_LEN = 15   # codes, numbers and short labels can't carry an instruction worth shielding
MAX_SHIELD_VALUES = 60


async def shield_rows(clients, settings, rows: list[list]) -> tuple[list[list], int]:
    """Indirect-injection shield for third-party text in query results. Every distinct string cell of at least
    MIN_SHIELD_LEN chars is sent as its own document (column names can be aliased by the generated SQL, so we
    don't trust them). Flagged values, and any beyond MAX_SHIELD_VALUES, are replaced with REMOVED."""
    if not settings.guardrails_enabled:
        return rows, 0
    values = list(dict.fromkeys(v for row in rows for v in row if isinstance(v, str) and len(v) >= MIN_SHIELD_LEN))
    checked = values[:MAX_SHIELD_VALUES]
    flags = await content_safety.shield_documents(clients, settings, checked)
    bad = {v for v, f in zip(checked, flags) if f} | set(values[MAX_SHIELD_VALUES:])
    if not bad:
        return rows, 0
    return [[REMOVED if v in bad else v for v in row] for row in rows], len(bad)
