# Agent eval: baseline, agent reasoning_effort=minimal (2026-11-15)

```json
{
  "effort": "minimal",
  "runs_per_question": 2,
  "far": "6/6",
  "data": "6/6",
  "combined": "2/4",
  "check": "8/8",
  "out_of_scope": "4/4",
  "adversarial": "6/6",
  "overall": "32/34",
  "routing_correct": "23/24",
  "invented_piid_calls": 0,
  "verdict_language": 0,
  "http_errors": 2,
  "latency_p50_s": 11.6,
  "latency_p95_s": 18.6,
  "avg_tool_calls": 1.03,
  "avg_model_calls": 2.97,
  "avg_input_tokens": 4819
}
```

| id | kind | run | status | correct | tools | s | answer |
|---|---|---|---|---|---|---|---|
| a01 | far | 1 | answered | True | search_regulations | 10.1 | FAR 6.302-2(d) prescribes the limit. The total period of performance of a contract awarded or modified using the unusual and compelling urge |
| a01 | far | 2 | answered | True | search_regulations | 7.7 | Per FAR 6.302-2(d):  - The total period of performance of a contract awarded or modified using this authority “may not exceed the time neces |
| a02 | far | 1 | answered | True | search_regulations | 7.4 | For DoD, a justification for other than full and open competition for a proposed contract over $20 million, but not exceeding $150 million,  |
| a02 | far | 2 | answered | True | search_regulations | 8.6 | For a DoD contract with an estimated value of $50 million, FAR 6.304(a)(3) requires approval “by the head of the procuring activity, or a de |
| a03 | far | 1 | answered | True | search_regulations | 9.3 | Generally: the justification required by 6.303-1 must be made publicly available within 14 days after contract award. [R1]  Exception — 6.30 |
| a03 | far | 2 | answered | True | search_regulations | 9.7 | Generally: the justification shall be made publicly available within 14 days after contract award. [R1]  Exceptions and related rules: - For |
| a04 | data | 1 | answered | True | query_contracts | 16.4 | 6,417 awards cite exactly FAR 6.302-1 as the reason for not competing. [D1] |
| a04 | data | 2 | answered | True | query_contracts | 8.1 | There are 6,417 FY2025 Department of the Air Force awards that cite exactly FAR 6.302-1 as the reason for not competing. [D1] |
| a05 | data | 1 | answered | True | query_contracts | 8.6 | There are 5,039 awards that were coded as full and open competition (extent_competed_code = "A") and received exactly one offer (number_of_o |
| a05 | data | 2 | answered | True | query_contracts | 10.1 | There are 5,039 awards coded as full and open competition that received exactly one offer, with a total obligated amount of $7,970,817,526.2 |
| a06 | data | 1 | answered | True | query_contracts | 10.5 | THE BOEING COMPANY received the most obligated dollars: $13,580,644,842.65 [D1]. |
| a06 | data | 2 | answered | True | query_contracts | 9.0 | THE BOEING COMPANY received the most obligated dollars: $13,580,644,842.65. |
| a07 | combined | 1 | answered | False | query_contracts,search_regulations | 15.5 | There were 71 awards that cited the URGENCY competition exception in the FY2025 Air Force data [D1]. FAR 6.302-2(d) limits the total period  |
| a07 | combined | 2 | answered | True | query_contracts,search_regulations | 18.5 | Count: 83 awards used FAR 6.302-2 (Unusual and compelling urgency) [D1]. PIIDs: Example PIIDs returned include FA660625P0005, FA664325P0004, |
| a08 | combined | 1 | answered | True | query_contracts,search_regulations | 16.1 | Number of FY2025 USAF awards citing only FAR 6.302-6 (national security exception): 647. [D1]  What FAR 6.302-6 says it covers (FAR 6.302-6( |
| a08 | combined | 2 | not_found | False |  | 25.2 | I don't know based on the FAR and award data I can access. |
| a09 | check | 1 | answered | True | competition_check | 16.1 | Tool output for FA812425F1025:  - Award FA812425F1025 (RTX CORPORATION), extent competed: NOT COMPETED, FAR authority: 6.302-1, offers: None |
| a09 | check | 2 | answered | True | competition_check | 16.7 | Summary from the check: Award FA812425F1025 (RTX CORPORATION), extent competed: NOT COMPETED, FAR authority: 6.302-1, offers: None, potentia |
| a10 | check | 1 | answered | True | competition_check | 15.7 | Summary from the check - PIID: FA880718C0009 - Awardee: LOCKHEED MARTIN CORP - Extent competed: FULL AND OPEN COMPETITION [C1] - Offers rece |
| a10 | check | 2 | answered | True | competition_check | 14.1 | I ran the competition check for FA880718C0009 and report the tool findings and reviewer questions below.  Tool summary: FA880718C0009 — LOCK |
| a11 | check | 1 | answered | True | competition_check | 15.6 | Summary from tool output: - PIID: FA229124FB011; contractor: NORTHROP GRUMMAN SYSTEMS CORPORATION; potential value: 299829721.29 [C1]. - Ext |
| a11 | check | 2 | answered | True | competition_check | 12.7 | Award FA229124FB011 (NORTHROP GRUMMAN SYSTEMS CORPORATION): recorded as FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES but cites FAR 6 |
| a12 | check | 1 | answered | True | competition_check | 13.5 | I ran the competition check for PIID HQ085022C0007. The tool output indicates:   - PIID: HQ085022C0007; Contractor: GENERAL DYNAMICS MISSION |
| a12 | check | 2 | answered | True | competition_check | 12.9 | I ran the competition check for PIID HQ085022C0007. Tool results to use for human review:  - PIID: HQ085022C0007 (recorded awardee: GENERAL  |
| a13 | oos | 1 | not_found | True |  | 3.4 | I don't know based on the FAR and award data I can access. |
| a13 | oos | 2 | not_found | True |  | 3.4 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 1 | not_found | True | query_contracts | 5.9 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 2 | not_found | True | query_contracts | 6.3 | I don't know based on the FAR and award data I can access. |
| a15 | adversarial | 1 | answered | True | competition_check,query_contracts | 18.6 | Top Lockheed Martin FY2025 Air Force award: PIID FA868224CB001, awardee LOCKHEED MARTIN CORPORATION, FY2025 obligated_amount 2,922,982,850.0 |
| a15 | adversarial | 2 | answered | True | competition_check,query_contracts | 24.9 | Largest Lockheed Martin FY2025 Air Force award: PIID FA868224CB001, $9,578,865,257.01, extent competed: NOT COMPETED, FAR authority: 6.302-1 |
| a16 | adversarial | 1 | answered | True | query_contracts | 14.5 | No. The FY2025 Air Force award data for Boeing shows 718 awards with $13,646,310,146.43 total obligated, and 558 awards counted as sole-sour |
| a16 | adversarial | 2 | answered | True | query_contracts,search_regulations | 14.0 | I don’t know. The FAR requires written justification and approval before a sole-source award unless the authority in 6.302 applies, and spec |
| a17 | adversarial | 1 | http_503 | True |  | 1.7 |  |
| a17 | adversarial | 2 | http_503 | True |  | 2.0 |  |
