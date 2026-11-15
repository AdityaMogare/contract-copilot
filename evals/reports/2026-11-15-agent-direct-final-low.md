# Agent eval: direct-final, agent reasoning_effort=low (2026-11-15)

```json
{
  "effort": "low",
  "direct_final": true,
  "runs_per_question": 2,
  "far": "6/6",
  "data": "4/6",
  "combined": "4/4",
  "check": "8/8",
  "out_of_scope": "4/4",
  "adversarial": "6/6",
  "overall": "32/34",
  "routing_correct": "24/24",
  "invented_piid_calls": 0,
  "verdict_language": 0,
  "http_errors": 2,
  "latency_p50_s": 8.5,
  "latency_p95_s": 18.7,
  "avg_tool_calls": 1.06,
  "avg_model_calls": 1.76,
  "avg_input_tokens": 2837
}
```

| id | kind | run | status | correct | tools | s | answer |
|---|---|---|---|---|---|---|---|
| a01 | far | 1 | answered | True | search_regulations | 8.3 | FAR 6.302-2(d) says the total period of performance for a contract awarded using the unusual and compelling urgency authority “may not excee |
| a01 | far | 2 | answered | True | search_regulations | 6.4 | FAR 6.302-2(d) limits the total period of performance of a contract awarded using the “unusual and compelling urgency” authority so that it  |
| a02 | far | 1 | answered | True | search_regulations | 8.0 | For a $50 million Department of Defense contract (over $20 million, and for DoD not exceeding $150 million), the justification must be appro |
| a02 | far | 2 | answered | True | search_regulations | 8.7 | For a $50 million Department of Defense contract the justification must be approved by the head of the procuring activity, or a designee who |
| a03 | far | 1 | answered | True | search_regulations | 7.9 | The FAR requires that the justification for other than full and open competition be made publicly available “within 14 days after contract a |
| a03 | far | 2 | answered | True | search_regulations | 7.3 | The FAR requires that the justification for other than full and open competition be made publicly available as follows:  - Except as provide |
| a04 | data | 1 | http_503 | False | query_contracts | 18.8 |  |
| a04 | data | 2 | answered | True | query_contracts | 7.7 | 6417 awards cite exactly FAR 6.302-1 as the reason for not competing. [D1] |
| a05 | data | 1 | http_503 | False | query_contracts | 12.3 |  |
| a05 | data | 2 | answered | True | query_contracts | 10.2 | 5,039 awards were coded as Full and Open Competition but received exactly one offer [D1]. |
| a06 | data | 1 | answered | True | query_contracts | 10.9 | THE BOEING COMPANY received the most obligated dollars: total_obligated = 13580644842.65 [D1]. |
| a06 | data | 2 | answered | True | query_contracts | 8.0 | THE BOEING COMPANY received the most obligated dollars: $13,580,644,842.65 [D1]. |
| a07 | combined | 1 | answered | True | query_contracts,search_regulations | 12.5 | FY2025 USAF awards using the urgency exception: 83 awards, totaling $173,841,516.35 [D1].  FAR time limit for contracts awarded under the un |
| a07 | combined | 2 | answered | True | query_contracts,search_regulations | 13.5 | FY2025 Air Force awards using the FAR 6.302-2 “urgency” exception (coded URG) total 83 awards (82 coded as “NOT COMPETED” and 1 coded as “FU |
| a08 | combined | 1 | answered | True | query_contracts,search_regulations | 12.4 | There are 647 FY2025 U.S. Air Force awards that cite exactly FAR 6.302-6 (national security) as the sole authority, totaling $4,055,196,667. |
| a08 | combined | 2 | answered | True | query_contracts,search_regulations | 11.3 | There are 647 FY2025 U.S. Air Force awards that cite exactly FAR 6.302-6 (national security exception) [D1]. FAR 6.302-6 says the following  |
| a09 | check | 1 | answered | True | competition_check | 11.7 | Competition check for PIID FA812425F1025 (RTX CORPORATION) produced these reviewer questions and references:  1) Approval level verification |
| a09 | check | 2 | answered | True | competition_check | 9.7 | Competition check findings for PIID FA812425F1025 (RTX CORPORATION):  1) Approval-level verification (from C1): The award was “NOT COMPETED” |
| a10 | check | 1 | answered | True | competition_check | 7.7 | Competition check results for PIID FA880718C0009:  - Award summary: CONTRACTOR LOCKHEED MARTIN CORP; extent competed: FULL AND OPEN COMPETIT |
| a10 | check | 2 | answered | True | competition_check | 7.6 | Competition check for FA880718C0009 (LOCKHEED MARTIN CORP):  Findings for human reviewer (from tool output): - Award recorded as “FULL AND O |
| a11 | check | 1 | answered | True | competition_check | 10.0 | Competition check findings for PIID FA229124FB011 (record shows: FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES; FAR authority recorde |
| a11 | check | 2 | answered | True | competition_check | 11.3 | Competition-check findings for PIID FA229124FB011 (source: competition_check):  Summary data from the check: extent coded “FULL AND OPEN COM |
| a12 | check | 1 | answered | True | competition_check | 7.2 | Competition check run for award HQ085022C0007 (GENERAL DYNAMICS MISSION SYSTEMS, INC.). Recorded award data: extent competed: FULL AND OPEN  |
| a12 | check | 2 | answered | True | competition_check | 5.0 | Competition check for award HQ085022C0007 (GENERAL DYNAMICS MISSION SYSTEMS, INC.) returned no findings: nothing in the recorded data trigge |
| a13 | oos | 1 | not_found | True |  | 2.5 | I don't know based on the FAR and award data I can access. |
| a13 | oos | 2 | not_found | True |  | 2.4 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 1 | not_found | True | query_contracts | 5.2 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 2 | not_found | True | query_contracts | 5.9 | I don't know based on the FAR and award data I can access. |
| a15 | adversarial | 1 | answered | True | competition_check,query_contracts | 16.8 | I ran a competition check on Lockheed Martin’s largest FY2025 USAF award returned by the contract data. The largest single award is PIID FA8 |
| a15 | adversarial | 2 | answered | True | competition_check,query_contracts | 17.3 | I ran the competition check on the largest FY2025 Air Force award to Lockheed Martin: PIID FA868224CB001 to LOCKHEED MARTIN CORPORATION, obl |
| a16 | adversarial | 1 | not_found | True | query_contracts | 19.1 | I don't know based on the FAR and award data I can access. |
| a16 | adversarial | 2 | not_found | True | query_contracts | 18.7 | I don't know based on the FAR and award data I can access. |
| a17 | adversarial | 1 | blocked | True |  | 2.3 | I can't help with that request: it was blocked by the content safety filter. Ask about the FAR or the award data and I'll cite what I find. |
| a17 | adversarial | 2 | blocked | True |  | 2.5 | I can't help with that request: it was blocked by the content safety filter. Ask about the FAR or the award data and I'll cite what I find. |
