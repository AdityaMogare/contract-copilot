"""Shared error classification."""

from __future__ import annotations

BLOCKED_TEXT = ("I can't help with that request: it was blocked by the content safety filter. "
                "Ask about the FAR or the award data and I'll cite what I find.")


def is_content_filter(e: BaseException | None) -> bool:
    """Azure OpenAI rejects filtered prompts with HTTP 400, code 'content_filter' (default jailbreak/harm filter).
    That's a safety outcome, not an outage: endpoints answer 200 {"status": "blocked"} instead of 503."""
    while e is not None:
        if getattr(e, "code", None) == "content_filter" or "content_filter" in str(e):
            return True
        e = e.__cause__ if e.__cause__ is not e else None
    return False
