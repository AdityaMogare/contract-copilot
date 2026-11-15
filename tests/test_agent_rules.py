"""Competition rules v1 (design 08 §4) on hand-built rows, incl. 6.304 tier boundaries."""

import pytest

from app.agent.rules import approval_tier, evaluate


def _row(**kw):
    base = {"award_key": "K", "piid": "P", "extent_competed_code": "A", "extent_competed": "FULL AND OPEN COMPETITION",
            "far_authority": None, "number_of_offers_received": 3, "potential_total_value": 1_000_000.0,
            "current_total_value": 500_000.0, "competition_source": "base_action", "fair_opportunity_limited_sources": None}
    return {**base, **kw}


def _ids(row):
    return sorted(f.rule_id for f in evaluate(row))


def test_clean_competed_award_has_no_findings():
    assert _ids(_row()) == []


def test_coding_conflict():
    f = evaluate(_row(far_authority="6.302-1(b)(1)", extent_competed_code="D"))
    assert [x.rule_id for x in f] == ["CODING-CONFLICT"]
    assert f[0].far_sections == ["6.302-1", "6.001"]   # paragraph trimmed to the indexed section


@pytest.mark.parametrize("value, cite", [
    (900_000, "6.304(a)(1)"), (900_001, "6.304(a)(2)"), (20_000_000, "6.304(a)(2)"),
    (20_000_001, "6.304(a)(3)"), (150_000_000, "6.304(a)(3)"), (150_000_001, "6.304(a)(4)"),
])
def test_approval_tier_boundaries(value, cite):
    assert approval_tier(value)[1] == cite


def test_not_competed_base_action_gets_approval_and_posting():
    f = {x.rule_id: x for x in evaluate(_row(extent_competed_code="C", far_authority="6.302-1",
                                             potential_total_value=25_000_000.0))}
    assert set(f) == {"APPROVAL-LEVEL", "JA-POSTING"}
    assert "head of the contracting activity" in f["APPROVAL-LEVEL"].statement
    assert f["APPROVAL-LEVEL"].evidence["tier"] == "6.304(a)(3)"
    assert "non-compliant" not in f["APPROVAL-LEVEL"].statement.lower()


def test_no_approval_finding_when_base_action_missing():
    # competition coding came from a later modification: the original approval value isn't known
    ids = _ids(_row(extent_competed_code="C", far_authority="6.302-1", competition_source="earliest_loaded_action"))
    assert ids == ["JA-POSTING"]


def test_urgency_also_flags_duration():
    ids = _ids(_row(extent_competed_code="C", far_authority="6.302-2", potential_total_value=500_000.0))
    assert ids == ["APPROVAL-LEVEL", "JA-POSTING", "URGENCY-DURATION"]


def test_single_offer_is_a_signal_not_a_violation():
    f = evaluate(_row(number_of_offers_received=1))
    assert [x.rule_id for x in f] == ["SINGLE-OFFER"] and "not a violation" in f[0].human_question


@pytest.mark.parametrize("fo, fires", [("FAIR OPPORTUNITY GIVEN", False), ("COMPETITIVE SET ASIDE", False),
                                       ("ONLY ONE SOURCE - OTHER", True), ("URGENCY", True), (None, False)])
def test_fair_opportunity(fo, fires):
    assert ("FAIR-OPPORTUNITY" in _ids(_row(fair_opportunity_limited_sources=fo))) is fires
