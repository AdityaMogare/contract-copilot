"""Azure AI Content Safety Prompt Shields on our AI Services account (design 10 §5 hop 2).

POST {endpoint}/contentsafety/text:shieldPrompt?api-version=2024-09-01
Auth: Entra bearer token, scope https://cognitiveservices.azure.com/.default; the caller needs the data action
ContentSafety/text:shieldprompt/action (custom role "Copilot Guardrails Caller", setup.sh step 8b).
Body: {"userPrompt": str ≤ 10,000 chars, "documents": [str] ≤ 5 (measured: a 6th → 400 InvalidRequestBody)}.
Failure modes: 401 (role missing / not yet propagated, measured), 429, timeout → HopError("content_safety").
"""

from __future__ import annotations

import asyncio

from opentelemetry import trace

from app.rag.retrieve import HopError

tracer = trace.get_tracer(__name__)
MAX_DOCS = 5
MAX_CHARS = 10_000


async def _post(clients, settings, body: dict) -> dict:
    url = f"{str(settings.azure_openai_endpoint).rstrip('/')}/contentsafety/text:shieldPrompt"
    try:
        token = await clients.token_provider()
        r = await clients.http.post(url, params={"api-version": settings.content_safety_api_version}, json=body,
                                    headers={"Authorization": f"Bearer {token}"}, timeout=settings.guard_timeout_s)
        r.raise_for_status()
        return r.json()
    except Exception as e:   # fail closed: the caller turns this into 503 {"hop": "content_safety"}
        raise HopError("content_safety", e) from e


async def shield_prompt(clients, settings, user_prompt: str) -> bool:
    """True if Prompt Shields flags the user prompt as a direct attack (jailbreak)."""
    with tracer.start_as_current_span("guard.shield_prompt") as span:
        out = await _post(clients, settings, {"userPrompt": user_prompt[:MAX_CHARS], "documents": []})
        attack = bool(out["userPromptAnalysis"]["attackDetected"])
        span.set_attribute("guard.attack", attack)
        return attack


async def shield_documents(clients, settings, docs: list[str]) -> list[bool]:
    """One flag per document (indirect attack). Batches of 5 run in parallel."""
    if not docs:
        return []
    with tracer.start_as_current_span("guard.shield_documents") as span:
        batches = [docs[i:i + MAX_DOCS] for i in range(0, len(docs), MAX_DOCS)]
        outs = await asyncio.gather(*(_post(clients, settings, {"userPrompt": "", "documents": [d[:MAX_CHARS] for d in b]})
                                      for b in batches))
        flags = [bool(d["attackDetected"]) for o in outs for d in o["documentsAnalysis"]]
        span.set_attribute("guard.documents", len(docs))
        span.set_attribute("guard.flagged", sum(flags))
        return flags
