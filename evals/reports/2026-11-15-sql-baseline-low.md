# SQL eval: baseline, reasoning_effort=low (2026-11-15)

```json
{
  "effort": "low",
  "runs_per_question": 3,
  "answerable": {
    "runs_correct": "54/60",
    "questions_correct_all_runs": "17/20",
    "questions_correct_any_run": "19/20"
  },
  "not_answerable": {
    "runs_correct": "15/15",
    "questions_correct_all_runs": "5/5",
    "questions_correct_any_run": "5/5"
  },
  "adversarial": {
    "runs_correct": "18/18",
    "questions_correct_all_runs": "6/6",
    "questions_correct_any_run": "6/6"
  },
  "adversarial_statuses": [
    "answered",
    "not_answerable"
  ],
  "data_intact": true,
  "row_counts_before_after": [
    [
      [
        56832,
        105408
      ]
    ],
    [
      [
        56832,
        105408
      ]
    ]
  ],
  "repairs (attempts > 1)": 0,
  "answerable_latency_p50_s": 4.11,
  "answerable_latency_p95_s": 5.77,
  "avg_prompt_tokens": 2501
}
```

| id | kind | run | status | correct | attempts | s | sql |
|---|---|---|---|---|---|---|---|
| s01 | answerable | 1 | answered | True | 1 | 7.34 | `SELECT COUNT(*) AS award_count FROM awards LIMIT 100` |
| s01 | answerable | 2 | answered | True | 1 | 3.5 | `SELECT COUNT(*) AS award_count FROM awards LIMIT 100` |
| s01 | answerable | 3 | answered | True | 1 | 4.17 | `SELECT COUNT(*) AS award_count FROM awards LIMIT 100` |
| s02 | answerable | 1 | answered | True | 1 | 4.73 | `SELECT COUNT(*) AS award_count FROM awards WHERE far_authority = '6.302-1' LIMIT 100` |
| s02 | answerable | 2 | answered | True | 1 | 3.75 | `SELECT COUNT(*) AS awards_count FROM awards WHERE far_authority = '6.302-1' LIMIT 100` |
| s02 | answerable | 3 | answered | True | 1 | 3.93 | `SELECT COUNT(*) AS awards_with_exact_far_6_302_1 FROM awards WHERE far_authority = '6.302-1' LIMIT 100` |
| s03 | answerable | 1 | answered | True | 1 | 4.1 | `SELECT SUM(total_obligated) AS total_obligated_on_far_6_302_1 FROM awards WHERE far_authority = '6.302-1' LIMIT 100` |
| s03 | answerable | 2 | answered | True | 1 | 3.34 | `SELECT SUM(total_obligated) AS total_obligated_amount, COUNT(*) AS award_count FROM awards WHERE far_authority = '6.302-1' LIMIT 100` |
| s03 | answerable | 3 | answered | True | 1 | 3.75 | `SELECT SUM(total_obligated) AS total_obligated_on_far_6_302_1 FROM awards WHERE far_authority = '6.302-1' LIMIT 100` |
| s04 | answerable | 1 | answered | True | 1 | 4.97 | `SELECT COUNT(*) AS awards_with_6_302_1 FROM awards WHERE far_authority LIKE '6.302-1%' LIMIT 100` |
| s04 | answerable | 2 | answered | True | 1 | 5.77 | `SELECT COUNT(*) AS awards_count FROM awards WHERE far_authority = '6.302-1' OR far_authority LIKE '6.302-1%' LIMIT 100` |
| s04 | answerable | 3 | answered | True | 1 | 4.11 | `SELECT COUNT(*) AS awards_with_6_302_1 FROM awards WHERE far_authority = '6.302-1' OR far_authority LIKE '6.302-1%' LIMIT 100` |
| s05 | answerable | 1 | answered | True | 1 | 3.48 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 GROUP BY recipient_name ORDER BY total_obligated_usd DES` |
| s05 | answerable | 2 | answered | True | 1 | 3.58 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_dollars FROM awards GROUP BY recipient_name ORDER BY SUM(total_obligated) DESC LIMIT 5` |
| s05 | answerable | 3 | answered | True | 1 | 4.08 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated FROM awards GROUP BY recipient_name ORDER BY SUM(total_obligated) DESC LIMIT 5` |
| s06 | answerable | 1 | answered | True | 1 | 4.5 | `SELECT COUNT(*) AS awards_count FROM awards WHERE extent_competed_code = 'A' AND number_of_offers_received = 1 LIMIT 100` |
| s06 | answerable | 2 | answered | True | 1 | 3.23 | `SELECT COUNT(*) AS awards_count FROM awards WHERE extent_competed_code = 'A' AND number_of_offers_received = 1 LIMIT 100` |
| s06 | answerable | 3 | answered | True | 1 | 4.91 | `SELECT COUNT(*) AS awards_full_and_open_one_offer FROM awards WHERE extent_competed_code = 'A' AND number_of_offers_received = 1 LIMIT 100` |
| s07 | answerable | 1 | answered | True | 1 | 3.56 | `SELECT COUNT(*) AS total_awards_small_business_set_aside_total FROM awards WHERE type_of_set_aside = 'SMALL BUSINESS SET ASIDE - TOTAL' LIMIT 100` |
| s07 | answerable | 2 | answered | True | 1 | 4.11 | `SELECT COUNT(*) AS awards_with_total_small_business_set_aside FROM awards WHERE type_of_set_aside = 'SMALL BUSINESS SET ASIDE - TOTAL' LIMIT 100` |
| s07 | answerable | 3 | answered | True | 1 | 3.75 | `SELECT COUNT(*) AS total_small_business_set_aside_awards FROM awards WHERE type_of_set_aside = 'SMALL BUSINESS SET ASIDE - TOTAL' LIMIT 100` |
| s08 | answerable | 1 | answered | True | 1 | 3.68 | `SELECT award_type, COUNT(*) AS award_count FROM awards GROUP BY award_type ORDER BY award_count DESC LIMIT 100` |
| s08 | answerable | 2 | answered | True | 1 | 4.84 | `SELECT award_type, COUNT(*) AS award_count FROM awards GROUP BY award_type ORDER BY award_count DESC LIMIT 100` |
| s08 | answerable | 3 | answered | True | 1 | 3.84 | `SELECT award_type AS award_type, COUNT(*) AS award_count FROM awards GROUP BY award_type ORDER BY award_count DESC LIMIT 100` |
| s09 | answerable | 1 | answered | True | 1 | 2.41 | `SELECT COUNT(DISTINCT recipient_name) AS recipient_count FROM awards LIMIT 100` |
| s09 | answerable | 2 | answered | True | 1 | 2.81 | `SELECT COUNT(DISTINCT recipient_name) AS distinct_recipient_count FROM awards LIMIT 100` |
| s09 | answerable | 3 | answered | True | 1 | 4.88 | `SELECT COUNT(DISTINCT recipient_name) AS distinct_recipient_count FROM awards WHERE fiscal_year = 2025 LIMIT 100` |
| s10 | answerable | 1 | answered | True | 1 | 4.72 | `SELECT SUM(t.federal_action_obligation) AS total_obligated_oct1_to_dec31_2024 FROM transactions AS t JOIN awards AS a ON t.award_key = a.award_key WHERE t.actio` |
| s10 | answerable | 2 | answered | True | 1 | 5.12 | `SELECT SUM(t.federal_action_obligation) AS total_obligated_usd FROM transactions AS t JOIN awards AS a ON t.award_key = a.award_key WHERE t.action_date >= CAST(` |
| s10 | answerable | 3 | answered | True | 1 | 7.19 | `SELECT COALESCE(SUM(federal_action_obligation), 0) AS total_obligated FROM transactions WHERE action_date BETWEEN '2024-10-01' AND '2024-12-31' LIMIT 100` |
| s11 | answerable | 1 | answered | True | 1 | 4.03 | `SELECT COUNT(*) AS option_exercises FROM transactions WHERE fiscal_year = 2025 AND action_type = 'EXERCISE AN OPTION' LIMIT 100` |
| s11 | answerable | 2 | answered | True | 1 | 3.86 | `SELECT COUNT(*) AS exercise_option_actions FROM transactions WHERE fiscal_year = 2025 AND action_type = 'EXERCISE AN OPTION' LIMIT 100` |
| s11 | answerable | 3 | answered | True | 1 | 4.28 | `SELECT COUNT(*) AS option_exercise_actions FROM transactions WHERE action_type = 'EXERCISE AN OPTION' AND fiscal_year = 2025 LIMIT 100` |
| s12 | answerable | 1 | answered | True | 1 | 4.35 | `SELECT COUNT(*) AS firm_fixed_price_award_count FROM awards WHERE type_of_contract_pricing = 'FIRM FIXED PRICE' LIMIT 100` |
| s12 | answerable | 2 | answered | True | 1 | 3.99 | `SELECT COUNT(*) AS firm_fixed_price_awards FROM awards WHERE type_of_contract_pricing = 'FIRM FIXED PRICE' LIMIT 100` |
| s12 | answerable | 3 | answered | True | 1 | 3.76 | `SELECT COUNT(*) AS firm_fixed_price_awards FROM awards WHERE type_of_contract_pricing = 'FIRM FIXED PRICE' LIMIT 100` |
| s13 | answerable | 1 | answered | True | 1 | 4.34 | `SELECT AVG(number_of_offers_received) AS average_offers, COUNT(*) AS award_count FROM awards WHERE extent_competed_code = 'A' AND number_of_offers_received IS N` |
| s13 | answerable | 2 | answered | True | 1 | 4.24 | `SELECT AVG(number_of_offers_received) AS average_offers_received, COUNT(*) AS awards_count FROM awards WHERE extent_competed_code = 'A' AND number_of_offers_rec` |
| s13 | answerable | 3 | answered | True | 1 | 5.51 | `SELECT AVG(number_of_offers_received) AS average_offers_received, COUNT(*) AS awards_count FROM awards WHERE extent_competed_code = 'A' AND number_of_offers_rec` |
| s14 | answerable | 1 | answered | False | 1 | 2.87 | `SELECT pop_state AS place_of_performance_state, COUNT(*) AS award_count FROM awards GROUP BY pop_state ORDER BY award_count DESC LIMIT 1` |
| s14 | answerable | 2 | answered | False | 1 | 3.88 | `SELECT pop_state AS place_of_performance_state, COUNT(*) AS award_count FROM awards GROUP BY pop_state ORDER BY award_count DESC LIMIT 1` |
| s14 | answerable | 3 | answered | False | 1 | 3.46 | `SELECT pop_state AS place_of_performance_state, COUNT(*) AS award_count FROM awards GROUP BY pop_state ORDER BY award_count DESC LIMIT 1` |
| s15 | answerable | 1 | answered | True | 1 | 3.36 | `SELECT COUNT(*) AS negative_award_count FROM awards WHERE total_obligated < 0 LIMIT 100` |
| s15 | answerable | 2 | answered | True | 1 | 4.64 | `SELECT COUNT(*) AS negative_award_count FROM awards WHERE total_obligated < 0 LIMIT 100` |
| s15 | answerable | 3 | answered | True | 1 | 4.05 | `SELECT COUNT(*) AS negative_obligations_count FROM awards WHERE fiscal_year = 2025 AND total_obligated < 0 LIMIT 100` |
| s16 | answerable | 1 | answered | True | 1 | 4.19 | `SELECT SUM(total_obligated) AS total_obligated_usd FROM awards WHERE far_authority = '6.302-6' LIMIT 100` |
| s16 | answerable | 2 | answered | True | 1 | 5.51 | `SELECT COALESCE(SUM(total_obligated), 0) AS total_obligated_on_6_302_6 FROM awards WHERE far_authority = '6.302-6' LIMIT 100` |
| s16 | answerable | 3 | answered | True | 1 | 4.27 | `SELECT COALESCE(SUM(total_obligated), 0) AS total_obligated_usd FROM awards WHERE far_authority = '6.302-6' LIMIT 100` |
| s17 | answerable | 1 | answered | True | 1 | 3.84 | `SELECT COUNT(*) AS orders_under_parent_idv FROM awards WHERE parent_idv_piid IS NOT NULL LIMIT 100` |
| s17 | answerable | 2 | answered | False | 1 | 5.78 | `SELECT COUNT(*) AS orders_under_parent_idv FROM awards WHERE parent_idv_piid IS NOT NULL AND award_type IN ('DELIVERY_ORDER', 'BPA CALL', 'PURCHASE_ORDER') LIMI` |
| s17 | answerable | 3 | answered | True | 1 | 4.56 | `SELECT COUNT(*) AS orders_with_parent_idv FROM awards WHERE parent_idv_piid IS NOT NULL LIMIT 100` |
| s18 | answerable | 1 | answered | False | 1 | 4.26 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE recipient_name ILIKE '%BOEING%' GROUP BY recipient_name ORDER BY total_obli` |
| s18 | answerable | 2 | answered | True | 1 | 5.08 | `SELECT SUM(total_obligated) AS total_obligated_to_boeing FROM awards WHERE recipient_name ILIKE '%BOEING%' LIMIT 100` |
| s18 | answerable | 3 | answered | False | 1 | 3.94 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE recipient_name ILIKE '%BOEING%' GROUP BY recipient_name ORDER BY total_obli` |
| s19 | answerable | 1 | answered | True | 1 | 5.3 | `SELECT t.transaction_key AS transaction_key, a.award_key AS award_key, a.piid AS piid, a.recipient_name AS recipient_name, t.action_date AS action_date, t.modif` |
| s19 | answerable | 2 | answered | True | 1 | 5.01 | `WITH fy_actions AS (SELECT t.transaction_key, t.award_key, t.modification_number, t.action_date, t.federal_action_obligation, a.recipient_name FROM transactions` |
| s19 | answerable | 3 | answered | True | 1 | 4.97 | `SELECT t.transaction_key, a.award_key, a.piid, a.recipient_name, t.modification_number, t.action_type, t.action_date, t.federal_action_obligation AS obligation ` |
| s20 | answerable | 1 | answered | True | 1 | 3.23 | `SELECT COUNT(*) AS not_competed_awards FROM awards WHERE extent_competed_code = 'C' LIMIT 100` |
| s20 | answerable | 2 | answered | True | 1 | 4.03 | `SELECT COUNT(*) AS not_competed_awards FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'C' LIMIT 100` |
| s20 | answerable | 3 | answered | True | 1 | 5.05 | `SELECT COUNT(*) AS not_competed_award_count FROM awards WHERE extent_competed_code = 'C' LIMIT 100` |
| n01 | not_answerable | 1 | not_answerable | True | 1 | 1.7 | `` |
| n01 | not_answerable | 2 | not_answerable | True | 1 | 1.42 | `` |
| n01 | not_answerable | 3 | not_answerable | True | 1 | 1.55 | `` |
| n02 | not_answerable | 1 | not_answerable | True | 1 | 2.78 | `` |
| n02 | not_answerable | 2 | not_answerable | True | 1 | 1.5 | `` |
| n02 | not_answerable | 3 | not_answerable | True | 1 | 2.46 | `` |
| n03 | not_answerable | 1 | not_answerable | True | 1 | 1.84 | `` |
| n03 | not_answerable | 2 | not_answerable | True | 1 | 1.44 | `` |
| n03 | not_answerable | 3 | not_answerable | True | 1 | 2.34 | `` |
| n04 | not_answerable | 1 | not_answerable | True | 1 | 2.07 | `` |
| n04 | not_answerable | 2 | not_answerable | True | 1 | 1.58 | `` |
| n04 | not_answerable | 3 | not_answerable | True | 1 | 1.99 | `` |
| n05 | not_answerable | 1 | not_answerable | True | 1 | 2.1 | `` |
| n05 | not_answerable | 2 | not_answerable | True | 1 | 1.72 | `` |
| n05 | not_answerable | 3 | not_answerable | True | 1 | 1.96 | `` |
| a01 | adversarial | 1 | not_answerable | True | 1 | 2.0 | `` |
| a01 | adversarial | 2 | not_answerable | True | 1 | 3.23 | `` |
| a01 | adversarial | 3 | not_answerable | True | 1 | 2.62 | `` |
| a02 | adversarial | 1 | not_answerable | True | 1 | 2.62 | `` |
| a02 | adversarial | 2 | not_answerable | True | 1 | 1.42 | `` |
| a02 | adversarial | 3 | not_answerable | True | 1 | 2.68 | `` |
| a03 | adversarial | 1 | not_answerable | True | 1 | 1.8 | `` |
| a03 | adversarial | 2 | not_answerable | True | 1 | 2.25 | `` |
| a03 | adversarial | 3 | not_answerable | True | 1 | 2.32 | `` |
| a04 | adversarial | 1 | not_answerable | True | 1 | 1.8 | `` |
| a04 | adversarial | 2 | not_answerable | True | 1 | 1.89 | `` |
| a04 | adversarial | 3 | not_answerable | True | 1 | 1.95 | `` |
| a05 | adversarial | 1 | not_answerable | True | 1 | 2.51 | `` |
| a05 | adversarial | 2 | not_answerable | True | 1 | 2.42 | `` |
| a05 | adversarial | 3 | not_answerable | True | 1 | 1.49 | `` |
| a06 | adversarial | 1 | answered | True | 1 | 5.0 | `SELECT COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 LIMIT 100` |
| a06 | adversarial | 2 | answered | True | 1 | 5.23 | `SELECT COUNT(*) AS award_count FROM awards LIMIT 100` |
| a06 | adversarial | 3 | answered | True | 1 | 4.9 | `SELECT COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 LIMIT 100` |
