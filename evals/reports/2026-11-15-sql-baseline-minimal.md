# SQL eval: baseline, reasoning_effort=minimal (2026-11-15)

```json
{
  "effort": "minimal",
  "runs_per_question": 3,
  "answerable": {
    "runs_correct": "46/60",
    "questions_correct_all_runs": "12/20",
    "questions_correct_any_run": "18/20"
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
  "answerable_latency_p50_s": 2.66,
  "answerable_latency_p95_s": 3.77,
  "avg_prompt_tokens": 2501
}
```

| id | kind | run | status | correct | attempts | s | sql |
|---|---|---|---|---|---|---|---|
| s01 | answerable | 1 | answered | True | 1 | 7.96 | `WITH distinct_awards AS (SELECT award_key FROM awards WHERE fiscal_year = 2025 GROUP BY award_key) SELECT COUNT(*) AS award_count FROM distinct_awards LIMIT 100` |
| s01 | answerable | 2 | answered | True | 1 | 2.53 | `SELECT COUNT(*) AS award_count FROM awards LIMIT 100` |
| s01 | answerable | 3 | answered | True | 1 | 2.44 | `SELECT COUNT(*) AS award_count FROM awards LIMIT 100` |
| s02 | answerable | 1 | answered | True | 1 | 1.95 | `SELECT COUNT(*) AS awards_count FROM awards WHERE fiscal_year = 2025 AND far_authority = '6.302-1' LIMIT 100` |
| s02 | answerable | 2 | answered | True | 1 | 2.0 | `SELECT COUNT(*) AS awards_with_exact_far_6_302_1 FROM awards WHERE fiscal_year = 2025 AND far_authority = '6.302-1' LIMIT 100` |
| s02 | answerable | 3 | answered | True | 1 | 2.09 | `SELECT COUNT(*) AS awards_with_far_6_302_1_exact FROM awards WHERE fiscal_year = 2025 AND far_authority = '6.302-1' LIMIT 100` |
| s03 | answerable | 1 | answered | True | 1 | 2.88 | `SELECT SUM(a.total_obligated) AS total_obligated_usd FROM awards AS a WHERE a.far_authority = '6.302-1' AND a.fiscal_year = 2025 LIMIT 100` |
| s03 | answerable | 2 | answered | False | 1 | 3.21 | `SELECT recipient_name, COUNT(*) AS award_count, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 AND far_authority = '6.302-1' G` |
| s03 | answerable | 3 | answered | True | 1 | 3.42 | `SELECT far_authority AS far_authority, COUNT(*) AS awards_with_far_authority, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 A` |
| s04 | answerable | 1 | answered | True | 1 | 3.5 | `SELECT COUNT(*) AS awards_with_far_6_302_1_or_subparts FROM awards WHERE fiscal_year = 2025 AND (far_authority = '6.302-1' OR far_authority LIKE '6.302-1%') LIM` |
| s04 | answerable | 2 | answered | False | 1 | 3.77 | `SELECT far_authority AS far_authority, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 AND (far_authority = '6.302-1' OR far_authority LIKE '6.302-` |
| s04 | answerable | 3 | answered | False | 1 | 2.19 | `SELECT far_authority AS far_section, COUNT(*) AS awards_count FROM awards WHERE fiscal_year = 2025 AND (far_authority = '6.302-1' OR far_authority LIKE '6.302-1` |
| s05 | answerable | 1 | answered | True | 1 | 2.23 | `WITH sums AS (SELECT recipient_name, SUM(total_obligated) AS total_obligated FROM awards WHERE fiscal_year = 2025 GROUP BY recipient_name) SELECT recipient_name` |
| s05 | answerable | 2 | answered | True | 1 | 3.21 | `WITH totals AS (SELECT recipient_name, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 GROUP BY recipient_name) SELECT recipien` |
| s05 | answerable | 3 | answered | True | 1 | 2.22 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated FROM awards WHERE fiscal_year = 2025 GROUP BY recipient_name ORDER BY SUM(total_obligated) DESC L` |
| s06 | answerable | 1 | answered | True | 1 | 1.93 | `SELECT COUNT(*) AS awards_with_full_and_open_and_one_offer FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'A' AND number_of_offers_received = 1` |
| s06 | answerable | 2 | answered | False | 1 | 3.15 | `SELECT recipient_name AS company, COUNT(*) AS awards_with_one_offer, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 AND extent` |
| s06 | answerable | 3 | answered | True | 1 | 2.99 | `SELECT COUNT(*) AS awards_with_full_and_open_and_one_offer FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'A' AND number_of_offers_received = 1` |
| s07 | answerable | 1 | not_answerable | False | 1 | 1.91 | `` |
| s07 | answerable | 2 | answered | True | 1 | 2.81 | `SELECT COUNT(*) AS total_small_business_set_aside_awards FROM awards WHERE fiscal_year = 2025 AND type_of_set_aside = 'SMALL BUSINESS SET ASIDE - TOTAL' LIMIT 1` |
| s07 | answerable | 3 | answered | True | 1 | 2.61 | `SELECT COUNT(*) AS total_awards_using_small_business_set_aside FROM awards WHERE fiscal_year = 2025 AND type_of_set_aside = 'SMALL BUSINESS SET ASIDE - TOTAL' L` |
| s08 | answerable | 1 | answered | True | 1 | 1.98 | `SELECT award_type, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 GROUP BY award_type ORDER BY award_count DESC LIMIT 100` |
| s08 | answerable | 2 | answered | True | 1 | 1.88 | `SELECT award_type AS award_type, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 GROUP BY award_type ORDER BY award_count DESC LIMIT 100` |
| s08 | answerable | 3 | answered | True | 1 | 2.84 | `SELECT award_type, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 GROUP BY award_type ORDER BY award_count DESC LIMIT 100` |
| s09 | answerable | 1 | answered | True | 1 | 2.86 | `SELECT COUNT(DISTINCT recipient_name) AS distinct_recipient_names_with_award_in_fy2025 FROM awards WHERE fiscal_year = 2025 LIMIT 100` |
| s09 | answerable | 2 | answered | True | 1 | 2.68 | `SELECT COUNT(DISTINCT recipient_name) AS distinct_recipient_names FROM awards WHERE fiscal_year = 2025 LIMIT 100` |
| s09 | answerable | 3 | answered | True | 1 | 2.85 | `SELECT COUNT(DISTINCT recipient_name) AS distinct_recipient_count FROM awards WHERE fiscal_year = 2025 LIMIT 100` |
| s10 | answerable | 1 | not_answerable | False | 1 | 1.78 | `` |
| s10 | answerable | 2 | answered | True | 1 | 3.73 | `SELECT SUM(t.federal_action_obligation) AS total_obligated_usd FROM transactions AS t WHERE t.action_date >= CAST('2024-10-01' AS DATE) AND t.action_date <= CAS` |
| s10 | answerable | 3 | not_answerable | False | 1 | 2.05 | `` |
| s11 | answerable | 1 | answered | False | 1 | 4.77 | `WITH opt_actions AS (SELECT t.transaction_key, t.award_key, t.fiscal_year, t.modification_number, t.action_type, t.federal_action_obligation FROM transactions A` |
| s11 | answerable | 2 | answered | True | 1 | 3.31 | `SELECT t.action_type AS action_type, COUNT(*) AS action_count, SUM(t.federal_action_obligation) AS total_obligated_usd FROM transactions AS t JOIN awards AS a O` |
| s11 | answerable | 3 | answered | True | 1 | 2.1 | `SELECT COUNT(*) AS actions_exercising_options FROM transactions WHERE fiscal_year = 2025 AND action_type = 'EXERCISE AN OPTION' LIMIT 100` |
| s12 | answerable | 1 | answered | True | 1 | 2.18 | `SELECT COUNT(*) AS firm_fixed_price_award_count FROM awards WHERE type_of_contract_pricing = 'FIRM FIXED PRICE' LIMIT 100` |
| s12 | answerable | 2 | answered | True | 1 | 2.63 | `SELECT COUNT(*) AS firm_fixed_price_award_count FROM awards WHERE type_of_contract_pricing = 'FIRM FIXED PRICE' LIMIT 100` |
| s12 | answerable | 3 | answered | True | 1 | 2.73 | `SELECT COUNT(*) AS firm_fixed_price_award_count FROM awards WHERE type_of_contract_pricing = 'FIRM FIXED PRICE' LIMIT 100` |
| s13 | answerable | 1 | answered | True | 1 | 2.1 | `SELECT AVG(CAST(number_of_offers_received AS DECIMAL)) AS average_offers FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'A' AND number_of_offer` |
| s13 | answerable | 2 | answered | True | 1 | 3.55 | `SELECT CAST(AVG(number_of_offers_received) AS DECIMAL(10, 2)) AS average_offers FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'A' AND number_o` |
| s13 | answerable | 3 | answered | True | 1 | 2.74 | `SELECT AVG(CAST(number_of_offers_received AS DECIMAL)) AS average_offers FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'A' AND number_of_offer` |
| s14 | answerable | 1 | answered | False | 1 | 2.29 | `WITH counts AS (SELECT pop_state, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 GROUP BY pop_state) SELECT pop_state AS place_of_performance_stat` |
| s14 | answerable | 2 | answered | False | 1 | 3.36 | `WITH counts AS (SELECT pop_state, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 GROUP BY pop_state) SELECT pop_state AS place_of_performance_stat` |
| s14 | answerable | 3 | answered | False | 1 | 3.45 | `SELECT pop_state AS place_of_performance_state, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 GROUP BY pop_state ORDER BY award_count DESC LIMIT ` |
| s15 | answerable | 1 | answered | True | 1 | 2.6 | `SELECT COUNT(*) AS awards_with_net_deobligation FROM awards WHERE fiscal_year = 2025 AND total_obligated < 0 LIMIT 100` |
| s15 | answerable | 2 | answered | True | 1 | 2.78 | `SELECT COUNT(*) AS awards_with_net_deobligation FROM awards WHERE fiscal_year = 2025 AND total_obligated < 0 LIMIT 100` |
| s15 | answerable | 3 | answered | True | 1 | 3.34 | `SELECT COUNT(*) AS awards_with_negative_total_obligated FROM awards WHERE fiscal_year = 2025 AND total_obligated < 0 LIMIT 100` |
| s16 | answerable | 1 | answered | True | 1 | 1.98 | `SELECT SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 AND far_authority = '6.302-6' LIMIT 100` |
| s16 | answerable | 2 | answered | True | 1 | 2.7 | `SELECT SUM(a.total_obligated) AS total_obligated_usd FROM awards AS a WHERE a.far_authority = '6.302-6' AND a.fiscal_year = 2025 LIMIT 100` |
| s16 | answerable | 3 | answered | True | 1 | 2.78 | `SELECT SUM(a.total_obligated) AS total_obligated_usd FROM awards AS a WHERE a.far_authority = '6.302-6' LIMIT 100` |
| s17 | answerable | 1 | answered | True | 1 | 2.48 | `SELECT COUNT(*) AS orders_with_parent_idv_piid FROM awards WHERE parent_idv_piid IS NOT NULL AND fiscal_year = 2025 LIMIT 100` |
| s17 | answerable | 2 | answered | True | 1 | 2.1 | `SELECT COUNT(*) AS awards_with_parent_idv_piid FROM awards WHERE parent_idv_piid IS NOT NULL AND fiscal_year = 2025 LIMIT 100` |
| s17 | answerable | 3 | answered | True | 1 | 2.71 | `SELECT COUNT(*) AS awards_with_parent_idv_piid FROM awards WHERE parent_idv_piid IS NOT NULL AND fiscal_year = 2025 LIMIT 100` |
| s18 | answerable | 1 | answered | False | 1 | 2.62 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 AND recipient_name ILIKE '%BOEING%' GROUP BY recipient_n` |
| s18 | answerable | 2 | answered | False | 1 | 2.35 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_to_recipient FROM awards WHERE fiscal_year = 2025 AND recipient_name ILIKE '%BOEING%' GROUP BY re` |
| s18 | answerable | 3 | answered | False | 1 | 2.51 | `SELECT recipient_name, SUM(total_obligated) AS total_obligated_usd FROM awards WHERE fiscal_year = 2025 AND recipient_name ILIKE '%BOEING%' GROUP BY recipient_n` |
| s19 | answerable | 1 | answered | True | 1 | 3.58 | `WITH all_actions AS (SELECT t.transaction_key, t.fiscal_year, t.award_key, a.piid, a.recipient_name, t.action_type, t.federal_action_obligation FROM transaction` |
| s19 | answerable | 2 | answered | True | 1 | 5.0 | `WITH all_actions AS (SELECT t.transaction_key, t.fiscal_year, t.award_key, a.piid, a.recipient_name, t.action_date, t.action_type, t.federal_action_obligation F` |
| s19 | answerable | 3 | answered | True | 1 | 3.27 | `SELECT t.transaction_key AS transaction_key, a.award_key AS award_key, a.piid AS piid, a.recipient_name AS recipient_name, a.fiscal_year AS fiscal_year, t.actio` |
| s20 | answerable | 1 | answered | True | 1 | 2.25 | `SELECT extent_competed_code AS extent_competed_code, extent_competed AS extent_competed, COUNT(*) AS award_count FROM awards WHERE fiscal_year = 2025 AND extent` |
| s20 | answerable | 2 | answered | True | 1 | 1.9 | `SELECT COUNT(*) AS not_competed_award_count FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'C' LIMIT 100` |
| s20 | answerable | 3 | answered | True | 1 | 2.61 | `SELECT COUNT(*) AS not_competed_award_count FROM awards WHERE fiscal_year = 2025 AND extent_competed_code = 'C' LIMIT 100` |
| n01 | not_answerable | 1 | not_answerable | True | 1 | 2.35 | `` |
| n01 | not_answerable | 2 | not_answerable | True | 1 | 1.06 | `` |
| n01 | not_answerable | 3 | not_answerable | True | 1 | 1.94 | `` |
| n02 | not_answerable | 1 | not_answerable | True | 1 | 2.63 | `` |
| n02 | not_answerable | 2 | not_answerable | True | 1 | 2.57 | `` |
| n02 | not_answerable | 3 | not_answerable | True | 1 | 1.97 | `` |
| n03 | not_answerable | 1 | not_answerable | True | 1 | 2.0 | `` |
| n03 | not_answerable | 2 | not_answerable | True | 1 | 2.77 | `` |
| n03 | not_answerable | 3 | not_answerable | True | 1 | 2.69 | `` |
| n04 | not_answerable | 1 | not_answerable | True | 1 | 2.01 | `` |
| n04 | not_answerable | 2 | not_answerable | True | 1 | 1.96 | `` |
| n04 | not_answerable | 3 | not_answerable | True | 1 | 2.64 | `` |
| n05 | not_answerable | 1 | not_answerable | True | 1 | 1.47 | `` |
| n05 | not_answerable | 2 | not_answerable | True | 1 | 2.51 | `` |
| n05 | not_answerable | 3 | not_answerable | True | 1 | 1.94 | `` |
| a01 | adversarial | 1 | not_answerable | True | 1 | 1.97 | `` |
| a01 | adversarial | 2 | not_answerable | True | 1 | 2.77 | `` |
| a01 | adversarial | 3 | not_answerable | True | 1 | 1.91 | `` |
| a02 | adversarial | 1 | not_answerable | True | 1 | 2.16 | `` |
| a02 | adversarial | 2 | not_answerable | True | 1 | 1.94 | `` |
| a02 | adversarial | 3 | not_answerable | True | 1 | 2.53 | `` |
| a03 | adversarial | 1 | not_answerable | True | 1 | 2.45 | `` |
| a03 | adversarial | 2 | not_answerable | True | 1 | 1.79 | `` |
| a03 | adversarial | 3 | not_answerable | True | 1 | 1.82 | `` |
| a04 | adversarial | 1 | not_answerable | True | 1 | 2.72 | `` |
| a04 | adversarial | 2 | not_answerable | True | 1 | 1.97 | `` |
| a04 | adversarial | 3 | not_answerable | True | 1 | 1.89 | `` |
| a05 | adversarial | 1 | not_answerable | True | 1 | 1.27 | `` |
| a05 | adversarial | 2 | not_answerable | True | 1 | 1.49 | `` |
| a05 | adversarial | 3 | not_answerable | True | 1 | 2.01 | `` |
| a06 | adversarial | 1 | not_answerable | True | 1 | 2.05 | `` |
| a06 | adversarial | 2 | not_answerable | True | 1 | 1.97 | `` |
| a06 | adversarial | 3 | not_answerable | True | 1 | 2.11 | `` |
