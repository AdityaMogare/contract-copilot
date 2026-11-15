"""USAspending prime-transaction CSV rows → `transactions` + `awards` rows (design 06 §4). Pure Python, testable."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

FAR_CITE = re.compile(r"FAR\s+(\d+\.\d+(?:-\d+)?)((?:\([0-9A-Za-z]+\))*)", re.I)

TX_COLS = ["transaction_key", "fiscal_year", "award_key", "modification_number", "action_date",
           "action_type", "federal_action_obligation", "description"]
AWARD_COLS = ["fiscal_year", "award_key", "piid", "parent_idv_piid", "award_type", "recipient_name",
              "recipient_uei", "naics_code", "naics_description", "psc_code", "psc_description", "description",
              "awarding_office", "pop_state", "first_action_date", "last_action_date", "action_count",
              "total_obligated", "current_total_value", "potential_total_value", "extent_competed_code",
              "extent_competed", "other_than_full_open_code", "other_than_full_open", "far_authority",
              "solicitation_procedures", "number_of_offers_received", "type_of_set_aside",
              "fair_opportunity_limited_sources", "type_of_contract_pricing", "commercial_item_procedures",
              "competition_source"]


def far_authority(label: str) -> str | None:
    """'ONLY ONE SOURCE-OTHER (FAR 6.302-1 OTHER)' → '6.302-1'; '(FAR 6.302-5(A)(2)(I))' → '6.302-5(a)(2)(i)'."""
    m = FAR_CITE.search(label or "")
    if not m or "-" not in m.group(1):          # 'FAR 13' (SAP) names a part, not a section
        return None
    return m.group(1) + m.group(2).lower()


def _n(s: str) -> str | None:
    s = (s or "").strip()
    return s or None


def _money(s: str) -> Decimal | None:
    s = (s or "").strip()
    return Decimal(s) if s else None


def _int(s: str) -> int | None:
    s = (s or "").strip()
    return int(float(s)) if s else None


def _date(s: str) -> date | None:
    s = (s or "").strip()
    return date.fromisoformat(s[:10]) if s else None


def build(rows: Iterable[dict], fiscal_year: int) -> tuple[list[tuple], list[tuple]]:
    """Returns (transactions, awards) as tuples in TX_COLS / AWARD_COLS order."""
    txs: list[tuple] = []
    by_award: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = r["contract_award_unique_key"]
        by_award[key].append(r)
        txs.append((r["contract_transaction_unique_key"], fiscal_year, key, _n(r["modification_number"]),
                    _date(r["action_date"]), _n(r["action_type"]), _money(r["federal_action_obligation"]),
                    _n(r["transaction_description"])))

    awards: list[tuple] = []
    for key, acts in by_award.items():
        acts.sort(key=lambda r: (r["action_date"], r["modification_number"]))
        base = next((r for r in acts if (r["modification_number"] or "").strip() == "0"), None)
        comp = base or acts[0]                       # competition coding: base action if we have it
        latest = acts[-1]                            # values: as of the latest action
        obligated = [m for m in (_money(r["federal_action_obligation"]) for r in acts) if m is not None]
        awards.append((
            fiscal_year, key, _n(latest["award_id_piid"]), _n(latest["parent_award_id_piid"]),
            _n(latest["award_type"]), _n(latest["recipient_name"]), _n(latest["recipient_uei"]),
            _n(latest["naics_code"]), _n(latest["naics_description"]),
            _n(latest["product_or_service_code"]), _n(latest["product_or_service_code_description"]),
            _n(latest["prime_award_base_transaction_description"]), _n(latest["awarding_office_name"]),
            _n(latest["primary_place_of_performance_state_code"]),
            _date(acts[0]["action_date"]), _date(latest["action_date"]), len(acts),
            sum(obligated) if obligated else None,
            _money(latest["current_total_value_of_award"]), _money(latest["potential_total_value_of_award"]),
            _n(comp["extent_competed_code"]), _n(comp["extent_competed"]),
            _n(comp["other_than_full_and_open_competition_code"]), _n(comp["other_than_full_and_open_competition"]),
            far_authority(comp["other_than_full_and_open_competition"]),
            _n(comp["solicitation_procedures"]), _int(comp["number_of_offers_received"]),
            _n(comp["type_of_set_aside"]), _n(comp["fair_opportunity_limited_sources"]),
            _n(comp["type_of_contract_pricing"]), _n(comp["commercial_item_acquisition_procedures"]),
            "base_action" if base else "earliest_loaded_action",
        ))
    return txs, awards
