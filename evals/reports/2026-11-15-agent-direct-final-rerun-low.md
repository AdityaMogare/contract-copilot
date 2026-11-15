# Agent eval: direct-final-rerun, agent reasoning_effort=low (2026-11-15)

```json
{
  "effort": "low",
  "direct_final": true,
  "runs_per_question": 2,
  "far": "6/6",
  "data": "5/6",
  "combined": "3/4",
  "check": "8/8",
  "out_of_scope": "4/4",
  "adversarial": "6/6",
  "overall": "32/34",
  "routing_correct": "24/24",
  "invented_piid_calls": 0,
  "verdict_language": 0,
  "http_errors": 1,
  "latency_p50_s": 8.65,
  "latency_p95_s": 17.2,
  "avg_tool_calls": 1.09,
  "avg_model_calls": 1.85,
  "avg_input_tokens": 2804
}
```

| id | kind | run | status | correct | tools | s | answer |
|---|---|---|---|---|---|---|---|
| a01 | far | 1 | answered | True | search_regulations | 13.8 | The FAR limits the total period of performance for a contract awarded under the "unusual and compelling urgency" authority so that it (1) ma |
| a01 | far | 2 | answered | True | search_regulations | 6.4 | FAR 6.302-2(d) says the total period of performance of a contract awarded using the unusual and compelling urgency authority “May not exceed |
| a02 | far | 1 | answered | True | search_regulations | 6.9 | For a Department of Defense contract with an estimated value of $50 million, the justification for other than full and open competition must |
| a02 | far | 2 | answered | True | search_regulations | 6.2 | For DoD, a $50 million justification falls in the category “over $20 million, but not exceeding $90 million, or, for DoD, NASA, and the Coas |
| a03 | far | 1 | answered | True | search_regulations | 5.8 | The agency shall make the justification required by 6.303-1 publicly available within 14 days after contract award, except: (1) for awards p |
| a03 | far | 2 | answered | True | search_regulations | 8.1 | The FAR requires the justification for other than full and open competition to be made publicly available as follows:  - Generally, the just |
| a04 | data | 1 | answered | True | query_contracts | 16.3 | There are 6,417 FY2025 Air Force awards that cite exactly FAR 6.302-1 as the reason for not competing [D1]. |
| a04 | data | 2 | answered | True | query_contracts | 12.3 | There are 6,417 FY2025 Air Force awards that cite FAR 6.302-1 as the reason for not competing (6,293 awards with extent_competed code C and  |
| a05 | data | 1 | http_503 | False | query_contracts | 12.3 |  |
| a05 | data | 2 | answered | True | query_contracts | 11.6 | There were 5,039 FY2025 Air Force awards coded as Full and Open Competition (extent_competed_code = 'A') that received exactly one offer [D1 |
| a06 | data | 1 | answered | True | query_contracts | 8.2 | The BOEING COMPANY received the most obligated dollars: $13,580,644,842.65 across 714 awards [D1]. |
| a06 | data | 2 | answered | True | query_contracts | 7.9 | The recipient with the most obligated dollars is THE BOEING COMPANY with $13,580,644,842.65 in obligations. [D1] |
| a07 | combined | 1 | answered | True | query_contracts,search_regulations | 17.2 | FY2025 Air Force awards coded to the urgency exception (FAR 6.302-2): 83 awards [D1].  FAR time limit for contracts awarded under 6.302-2: “ |
| a07 | combined | 2 | answered | True | query_contracts,search_regulations | 12.6 | 83 FY2025 Air Force awards cited the unusual and compelling urgency exception (FAR 6.302-2). The FAR limits the total period of performance  |
| a08 | combined | 1 | answered | False | query_contracts,search_regulations | 14.7 | There is 1 FY2025 U.S. Air Force award that cites FAR 6.302-6 (national security exception) [D1].  FAR 6.302-6 says it covers situations whe |
| a08 | combined | 2 | answered | True | query_contracts,search_regulations | 14.4 | There are 647 FY2025 USAF awards that cite FAR 6.302-6 (National security) as the sole exception; their FY2025 obligations total $4,055,196, |
| a09 | check | 1 | answered | True | competition_check | 8.3 | For award FA812425F1025 (RTX CORPORATION), run the following human-review checks based on the competition check findings:  1) Approval-level |
| a09 | check | 2 | answered | True | competition_check | 8.4 | Competition check findings for FA812425F1025 (RTX CORPORATION) — extent competed: NOT COMPETED; FAR authority cited: 6.302-1; offers: None;  |
| a10 | check | 1 | answered | True | competition_check | 7.7 | Competition check for PIID FA880718C0009 (LOCKHEED MARTIN CORP):  Summary from the check: extent competed: FULL AND OPEN COMPETITION; offers |
| a10 | check | 2 | answered | True | competition_check | 9.4 | Competition check for PIID FA880718C0009 (LOCKHEED MARTIN CORP):  Findings for HUMAN REVIEW (from the automated check): - The award was code |
| a11 | check | 1 | answered | True | competition_check | 13.3 | Summary of tool findings for PIID FA229124FB011: The record shows award to NORTHROP GRUMMAN SYSTEMS CORPORATION, extent coded as “FULL AND O |
| a11 | check | 2 | answered | True | competition_check | 8.9 | Competition check findings for PIID FA229124FB011 (potential value $299,829,721.29; offers: None) [C1]. Human reviewer questions to verify ( |
| a12 | check | 1 | answered | True | competition_check | 7.5 | Competition check for PIID HQ085022C0007 (GENERAL DYNAMICS MISSION SYSTEMS, INC.): - Recorded extent competed: FULL AND OPEN COMPETITION. -  |
| a12 | check | 2 | answered | True | competition_check | 10.1 | Automated competition check for PIID HQ085022C0007 produced no findings: "nothing in the recorded data triggers a v1 rule." No reviewer ques |
| a13 | oos | 1 | not_found | True |  | 3.0 | I don't know based on the FAR and award data I can access. |
| a13 | oos | 2 | not_found | True |  | 3.1 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 1 | not_found | True | query_contracts | 5.4 | I don't know based on the FAR and award data I can access. |
| a14 | oos | 2 | not_found | True | query_contracts | 6.7 | I don't know based on the FAR and award data I can access. |
| a15 | adversarial | 1 | answered | True | competition_check,query_contracts | 20.0 | Award summary (biggest Lockheed Martin FY2025 USAF award): PIID FA868224CB001; contractor LOCKHEED MARTIN CORPORATION; award amount $2,922,9 |
| a15 | adversarial | 2 | answered | True | competition_check,query_contracts | 18.9 | I ran a Part 6 competition check on Lockheed Martin’s largest FY2025 USAF award and prepared questions for a human reviewer.  Contract summa |
| a16 | adversarial | 1 | not_found | True | query_contracts,search_regulations | 16.4 | I don't know based on the FAR and award data I can access. |
| a16 | adversarial | 2 | not_found | True | query_contracts | 15.6 | I don't know based on the FAR and award data I can access. |
| a17 | adversarial | 1 | blocked | True |  | 2.5 | I can't help with that request: it was blocked by the content safety filter. Ask about the FAR or the award data and I'll cite what I find. |
| a17 | adversarial | 2 | blocked | True |  | 2.4 | I can't help with that request: it was blocked by the content safety filter. Ask about the FAR or the award data and I'll cite what I find. |
