"""PII masking with Azure AI Language on the same AI Services account (design 10 §5 hop 2).

POST {endpoint}/language/:analyze-text?api-version=2024-11-01, kind PiiEntityRecognition.
Auth: same token/scope as the shield; data action Language/analyze-text/action.
Only contact/ID categories are masked. Names are kept on purpose: they're question subjects and public record.
"""

from __future__ import annotations

import re
from collections import Counter

from opentelemetry import trace

from app.rag.retrieve import HopError

tracer = trace.get_tracer(__name__)

CATEGORIES = {   # Language category → mask token
    "Email": "[EMAIL]", "PhoneNumber": "[PHONE]", "USSocialSecurityNumber": "[SSN]",
    "CreditCardNumber": "[CREDIT_CARD]", "USBankAccountNumber": "[BANK_ACCOUNT]", "IPAddress": "[IP_ADDRESS]",
    "USUKPassportNumber": "[PASSPORT]", "USDriversLicenseNumber": "[DRIVERS_LICENSE]", "Address": "[ADDRESS]",
}
# Measured: DFARS clause numbers ("252.204-7012") come back as PhoneNumber at confidence 0.65. Masking them would
# break the product ("Does DFARS [PHONE] apply?"), so a PhoneNumber that is exactly a clause number is kept.
CLAUSE_NUMBER = re.compile(r"^\d{1,3}\.\d{3}-\d{1,4}$")


def apply(text: str, entities: list[dict]) -> tuple[str, list[dict]]:
    """Replace entity spans (code-point offsets) with mask tokens. Returns masked text and redaction counts
    (categories only, never values)."""
    keep = [e for e in entities if e["category"] in CATEGORIES
            and not (e["category"] == "PhoneNumber" and CLAUSE_NUMBER.match(e["text"]))]
    out, pos, counts = [], 0, Counter()
    for e in sorted(keep, key=lambda e: e["offset"]):
        if e["offset"] < pos:          # overlapping entities: the first one already covers it
            continue
        out += [text[pos:e["offset"]], CATEGORIES[e["category"]]]
        pos = e["offset"] + e["length"]
        counts[e["category"]] += 1
    out.append(text[pos:])
    return "".join(out), [{"category": c, "count": n} for c, n in sorted(counts.items())]


async def mask(clients, settings, text: str) -> tuple[str, list[dict]]:
    with tracer.start_as_current_span("guard.pii") as span:
        url = f"{str(settings.azure_openai_endpoint).rstrip('/')}/language/:analyze-text"
        body = {"kind": "PiiEntityRecognition",
                "parameters": {"piiCategories": list(CATEGORIES), "stringIndexType": "UnicodeCodePoint"},
                "analysisInput": {"documents": [{"id": "1", "language": "en", "text": text}]}}
        try:
            token = await clients.token_provider()
            r = await clients.http.post(url, params={"api-version": settings.language_api_version}, json=body,
                                        headers={"Authorization": f"Bearer {token}"}, timeout=settings.guard_timeout_s)
            r.raise_for_status()
            doc = r.json()["results"]["documents"][0]
        except Exception as e:
            raise HopError("content_safety", e) from e
        masked, redactions = apply(text, doc["entities"])
        span.set_attribute("guard.pii_redactions", sum(x["count"] for x in redactions))
        return masked, redactions
