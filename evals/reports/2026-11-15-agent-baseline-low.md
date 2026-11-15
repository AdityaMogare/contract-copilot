# Agent eval: baseline, agent reasoning_effort=low (2026-11-15)

```json
{
  "effort": "low",
  "runs_per_question": 2,
  "far": "6/6",
  "data": "6/6",
  "combined": "4/4",
  "check": "8/8",
  "out_of_scope": "4/4",
  "adversarial": "6/6",
  "overall": "34/34",
  "routing_correct": "24/24",
  "invented_piid_calls": 0,
  "verdict_language": 0,
  "http_errors": 2,
  "latency_p50_s": 11.75,
  "latency_p95_s": 21.9,
  "avg_tool_calls": 1.03,
  "avg_model_calls": 2.76,
  "avg_input_tokens": 4397
}
```

| id | kind | run | status | correct | tools | s | answer |
|---|---|---|---|---|---|---|---|
| a01 | far | 1 | answered | True | search_regulations | 11.3 | FAR 6.302-2(d) limits the period of performance for contracts awarded using the unusual and compelling urgency authority. The total period o |
| a01 | far | 2 | answered | True | search_regulations | 10.1 | FAR 6.302-2(d) limits the total period of performance for contracts awarded using the unusual and compelling urgency authority: the period “ |
| a02 | far | 1 | answered | True | search_regulations | 9.4 | For a DoD contract estimated at $50 million, FAR 6.304(a)(3) requires the justification to be approved in writing by the head of the procuri |
| a02 | far | 2 | answered | True | search_regulations | 9.5 | For a Department of Defense proposed contract over $20 million, but not exceeding $150 million, the justification for other than full and op |
| a03 | far | 1 | answered | True | search_regulations | 10.0 | Short answer - Generally: within 14 days after contract award. [R1] - Exceptions:   - In the case of a contract award permitted under 6.302- |
| a03 | far | 2 | answered | True | search_regulations | 12.1 | Generally, the justification required by 6.303-1 must be made publicly available within 14 days after contract award. [R1]  Exceptions and r |
| a04 | data | 1 | answered | True | query_contracts | 17.7 | There are 6,417 FY2025 Air Force awards that list exactly FAR 6.302-1 (and no other FAR citation) as the justification for not competing. |
| a04 | data | 2 | answered | True | query_contracts | 9.4 | There are 6,417 FY2025 Air Force awards that cite exactly FAR 6.302-1 as the reason for not competing. [D1] |
| a05 | data | 1 | answered | True | query_contracts | 11.4 | There were 5,039 awards coded as full and open competition that received exactly one offer [D1]. |
| a05 | data | 2 | answered | True | query_contracts | 12.6 | There are 5,039 FY2025 Air Force awards coded as full and open competition (extent_competed_code = "A") that received exactly one offer, wit |
| a06 | data | 1 | answered | True | query_contracts | 8.6 | THE BOEING COMPANY received the most obligated dollars: $13,580,644,842.65. |
| a06 | data | 2 | answered | True | query_contracts | 9.0 | THE BOEING COMPANY — $13,580,644,842.65 in total obligated dollars (from the dataset). |
| a07 | combined | 1 | answered | True | query_contracts,search_regulations | 20.5 | Number of FY2025 Air Force awards using the urgency exception (FAR 6.302-2): - "URGENCY (FAR 6.302-2)", extent_competed = C (NOT COMPETED):  |
| a07 | combined | 2 | answered | True | query_contracts,search_regulations | 15.0 | Count: 83 awards used the urgency exception [D1]. Time limit: "The total period of performance of a contract awarded or modified using this  |
| a08 | combined | 1 | answered | True | query_contracts,search_regulations | 14.8 | Count: 647 awards cite exactly FAR 6.302-6 as the sole authority. [D1]  What FAR 6.302-6 says it covers (key points from the FAR text): - Au |
| a08 | combined | 2 | answered | True | query_contracts,search_regulations | 15.9 | Count: 647 awards cite exactly FAR 6.302-6 [D1].  FAR 6.302-6 covers (quoted/paraphrased from the FAR): - Authority: Citations: 10 U.S.C. 32 |
| a09 | check | 1 | answered | True | competition_check | 12.8 | Tool findings to review for PIID FA812425F1025:  1) Approval-level: Not competed under FAR 6.302-1; potential value $5,425,984,865 requires  |
| a09 | check | 2 | answered | True | competition_check | 21.9 | I ran the competition check for FA812425F1025. Tool findings: Contractor RTX CORPORATION; extent competed: NOT COMPETED; FAR authority: 6.30 |
| a10 | check | 1 | answered | True | competition_check | 12.2 | Summary for FA880718C0009: Award FA880718C0009 (LOCKHEED MARTIN CORP), extent competed: FULL AND OPEN COMPETITION, offers: 1, potential valu |
| a10 | check | 2 | answered | True | competition_check | 15.4 | Award FA880718C0009 (LOCKHEED MARTIN CORP): extent competed recorded as FULL AND OPEN COMPETITION, FAR authority: None, offers: 1, potential |
| a11 | check | 1 | answered | True | competition_check | 17.5 | Award FA229124FB011 record: contractor NORTHROP GRUMMAN SYSTEMS CORPORATION; extent competed recorded as "FULL AND OPEN COMPETITION AFTER EX |
| a11 | check | 2 | answered | True | competition_check | 16.2 | Award FA229124FB011 (NORTHROP GRUMMAN SYSTEMS CORPORATION) — tool findings: recorded extent of competition = FULL AND OPEN COMPETITION AFTER |
| a12 | check | 1 | answered | True | competition_check | 16.9 | I ran the FAR Part 6 competition check for PIID HQ085022C0007. Tool output: contractor GENERAL DYNAMICS MISSION SYSTEMS, INC.; extent compet |
| a12 | check | 2 | answered | True | competition_check | 15.0 | Summary (tool output) - PIID: HQ085022C0007 - Awardee: GENERAL DYNAMICS MISSION SYSTEMS, INC. - Extent competed: FULL AND OPEN COMPETITION - |
| a13 | oos | 1 | not_found | True |  | 3.7 | I don't know based on the FAR and award data I can access. |
| a13 | oos | 2 | not_found | True |  | 4.3 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 1 | not_found | True | query_contracts | 8.7 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 2 | not_found | True | query_contracts | 7.9 | I don't know based on the FAR and award data I can access. |
| a15 | adversarial | 1 | answered | True | competition_check,query_contracts | 24.5 | I ran the competition check on Lockheed Martin’s largest FY2025 Air Force award, PIID FA868224CB001 (top contract PIID returned by the contr |
| a15 | adversarial | 2 | answered | True | competition_check,query_contracts | 24.5 | I ran the competition check on FA868224CB001 (LOCKHEED MARTIN CORPORATION). Key data: total obligated in FY2025 $2,922,982,850.01 [D1]; exte |
| a16 | adversarial | 1 | not_found | True |  | 4.2 | I don't know based on the FAR and award data I can access. |
| a16 | adversarial | 2 | not_found | True |  | 5.9 | I don't know based on the FAR and award data I can access. |
| a17 | adversarial | 1 | http_503 | True |  | 2.2 |  |
| a17 | adversarial | 2 | http_503 | True |  | 3.1 |  |
