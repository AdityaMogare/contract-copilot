"""Competition-check rules v1 (design 08 §4). Pure functions over one `awards` row.

Each rule produces a FINDING: what the data shows, the FAR sections that apply, and the question a human
reviewer must answer. Rules never say "non-compliant": the data lacks the J&A documents, approvals and
periods of performance that a compliance decision needs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

RULES_VERSION = "v1"
NOT_COMPETED = {"B", "C"}          # not available for competition, not competed
COMPETED = {"A", "D", "F"}         # full and open, after exclusion of sources, competed under SAP
FAIR_OPP_OK = {"FAIR OPPORTUNITY GIVEN", "COMPETITIVE SET ASIDE"}

# FAR 6.304(a) approval levels. Air Force = DoD, so the DoD/NASA/Coast Guard $150M variant of (a)(3)/(a)(4) applies.
# The competition-check service verifies at runtime that the indexed 6.304 text still contains these amounts.
APPROVAL_TIERS = [
    (900_000, "the contracting officer's certification", "6.304(a)(1)"),
    (20_000_000, "the competition advocate", "6.304(a)(2)"),
    (150_000_000, "the head of the contracting activity (or designee)", "6.304(a)(3)"),
    (math.inf, "the senior procurement executive", "6.304(a)(4)"),
]
THRESHOLD_TEXT = ["$900,000", "$20 million", "$150 million"]


@dataclass
class Finding:
    rule_id: str
    statement: str
    human_question: str
    far_sections: list[str]
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def approval_tier(value: float | None) -> tuple[str, str] | None:
    if value is None:
        return None
    for limit, who, cite in APPROVAL_TIERS:
        if value <= limit:
            return who, cite
    return None


def _money(v) -> str:
    return f"${float(v):,.0f}" if v is not None else "unknown"


def _section(authority: str | None) -> str | None:
    """'6.302-1(b)(1)' → '6.302-1' (the indexed section)."""
    return authority.split("(")[0] if authority else None


def evaluate(a: dict) -> list[Finding]:
    code, auth = a.get("extent_competed_code"), a.get("far_authority")
    sec = _section(auth)
    out: list[Finding] = []

    if auth and auth.startswith("6.302") and code in COMPETED:
        out.append(Finding(
            "CODING-CONFLICT",
            f"Recorded as competed ({a.get('extent_competed')}) but cites a non-competition authority (FAR {auth}).",
            "Which is correct: was this award competed, or awarded under the cited exception?",
            [sec, "6.001"],
            {"extent_competed_code": code, "far_authority": auth}))

    if code in NOT_COMPETED and auth and auth.startswith("6.302"):
        value = a.get("potential_total_value") if a.get("potential_total_value") is not None else a.get("current_total_value")
        tier = approval_tier(float(value) if value is not None else None)
        if tier and a.get("competition_source") == "base_action":
            who, cite = tier
            out.append(Finding(
                "APPROVAL-LEVEL",
                f"Not competed under FAR {auth}; potential value {_money(value)} requires J&A approval by {who} (FAR {cite}).",
                f"Was the justification approved by {who} as FAR {cite} requires for this value?",
                ["6.304", "6.303-2", sec],
                {"extent_competed_code": code, "far_authority": auth, "value_used": float(value), "tier": cite}))
        out.append(Finding(
            "JA-POSTING",
            f"Not competed under FAR {auth}: the justification must be made publicly available.",
            "Was the J&A posted publicly within the time FAR 6.305 requires (or an exception documented)?",
            ["6.305", sec],
            {"extent_competed_code": code, "far_authority": auth}))

    if sec == "6.302-2":
        out.append(Finding(
            "URGENCY-DURATION",
            "Awarded under unusual and compelling urgency (FAR 6.302-2), which limits the contract period.",
            "Is the period of performance, including options, one year or less, or is there a head-of-agency "
            "determination of exceptional circumstances? (Period of performance isn't in the loaded data.)",
            ["6.302-2"],
            {"far_authority": auth}))

    if code == "A" and a.get("number_of_offers_received") == 1:
        out.append(Finding(
            "SINGLE-OFFER",
            "Full and open competition, but only one offer was received.",
            "Was the competition meaningful (requirement breadth, response time, market research)? "
            "A signal for review, not a violation. DoD's single-offer rules (DFARS 215.371) aren't in the indexed FAR.",
            ["6.101"],
            {"extent_competed_code": code, "number_of_offers_received": 1}))

    fo = a.get("fair_opportunity_limited_sources")
    if fo and fo not in FAIR_OPP_OK:
        out.append(Finding(
            "FAIR-OPPORTUNITY",
            f"Order placed with a fair-opportunity exception: {fo}.",
            "Is the exception justified in writing as FAR 16.505(b)(2) requires?",
            ["16.505"],
            {"fair_opportunity_limited_sources": fo}))

    for f in out:
        f.far_sections = list(dict.fromkeys(s for s in f.far_sections if s))
    return out
