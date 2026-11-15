"""Design 06 transform rules, on labels seen in the real FY2025 Q1 Air Force download."""

from decimal import Decimal

import pytest

from awards.transform import AWARD_COLS, build, far_authority


@pytest.mark.parametrize("label, expected", [
    ("ONLY ONE SOURCE-OTHER (FAR 6.302-1 OTHER)", "6.302-1"),
    ("AUTHORIZED BY STATUTE (FAR 6.302-5(A)(2)(I))", "6.302-5(a)(2)(i)"),
    ("FOLLOW-ON CONTRACT (FAR 6.302-1(A)(2)(II/III))", "6.302-1(a)(2)"),   # stops before the '/' range
    ("UNIQUE SOURCE (FAR 6.302-1(B)(1))", "6.302-1(b)(1)"),
    ("NATIONAL SECURITY (FAR 6.302-6)", "6.302-6"),
    ("SAP NON-COMPETITION (FAR 13)", None),                              # a part, not a section
    ("", None),
])
def test_far_authority(label, expected):
    assert far_authority(label) == expected


def _row(key, mod, date, oblig, **kw):
    base = {"contract_transaction_unique_key": f"{key}-{mod}-{date}", "contract_award_unique_key": key,
            "modification_number": mod, "action_date": date, "action_type": "", "federal_action_obligation": oblig,
            "transaction_description": "", "award_id_piid": "P1", "parent_award_id_piid": "", "award_type": "DEFINITIVE CONTRACT",
            "recipient_name": "ACME", "recipient_uei": "U1", "naics_code": "541330", "naics_description": "ENG",
            "product_or_service_code": "R425", "product_or_service_code_description": "ENG SVCS",
            "prime_award_base_transaction_description": "desc", "awarding_office_name": "AFLCMC",
            "primary_place_of_performance_state_code": "OH", "current_total_value_of_award": "100",
            "potential_total_value_of_award": "200", "extent_competed_code": "A", "extent_competed": "FULL AND OPEN COMPETITION",
            "other_than_full_and_open_competition_code": "", "other_than_full_and_open_competition": "",
            "solicitation_procedures": "NEGOTIATED PROPOSAL/QUOTE", "number_of_offers_received": "3",
            "type_of_set_aside": "", "fair_opportunity_limited_sources": "", "type_of_contract_pricing": "FIRM FIXED PRICE",
            "commercial_item_acquisition_procedures": ""}
    return {**base, **kw}


def _award(awards, key):
    return dict(zip(AWARD_COLS, next(a for a in awards if a[1] == key)))


def test_competition_from_base_action_when_present():
    rows = [_row("K1", "1", "2024-11-01", "10", extent_competed_code="C",
                 other_than_full_and_open_competition="ONLY ONE SOURCE-OTHER (FAR 6.302-1 OTHER)"),
            _row("K1", "0", "2024-10-05", "90")]
    txs, awards = build(rows, 2025)
    a = _award(awards, "K1")
    assert a["competition_source"] == "base_action" and a["extent_competed_code"] == "A" and a["far_authority"] is None
    assert a["total_obligated"] == Decimal("100") and a["action_count"] == 2 and len(txs) == 2
    assert str(a["first_action_date"]) == "2024-10-05" and str(a["last_action_date"]) == "2024-11-01"


def test_competition_from_earliest_action_when_base_missing():
    rows = [_row("K2", "P00003", "2025-02-01", "-5"),
            _row("K2", "P00002", "2024-12-01", "7", extent_competed_code="C",
                 other_than_full_and_open_competition="NATIONAL SECURITY (FAR 6.302-6)")]
    _, awards = build(rows, 2025)
    a = _award(awards, "K2")
    assert a["competition_source"] == "earliest_loaded_action" and a["far_authority"] == "6.302-6"
    assert a["total_obligated"] == Decimal("2")


def test_empty_numbers_become_null():
    _, awards = build([_row("K3", "0", "2025-01-01", "", number_of_offers_received="",
                            current_total_value_of_award="")], 2025)
    a = _award(awards, "K3")
    assert a["number_of_offers_received"] is None and a["current_total_value"] is None and a["total_obligated"] is None
