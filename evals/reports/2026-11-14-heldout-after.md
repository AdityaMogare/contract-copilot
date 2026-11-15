# Eval: heldout-after (2026-11-14)

Config: index alias `far-chunks-v2`, top_k=8, reasoning_effort=low, vector_weight=3.0, chat=`chat`, embed dims=512. Golden set: `evals/golden.jsonl`.

| Metric | Value |
|---|---|
| questions | 12 |
| errors | 0 |
| retrieval_hit@k (answerable) | 9/10 (90%) |
| answered_or_partial (answerable) | 10/10 (100%) |
| fully_answered (answerable) | 9/10 (90%) |
| citation_hit (answerable, any expected section cited) | 9/10 (90%) |
| false_idk (answerable → not_found) | 0/10 (0%) |
| correct_idk (unanswerable → not_found) | 2/2 (100%) |
| validation_failed | 0 |
| retries (attempts > 1) | 0 |
| latency_p50_s | 3.6 |
| latency_p95_s | 6.85 |
| avg_prompt_tokens | 3215 |
| avg_completion_tokens (incl. reasoning) | 288 |

| id | answerable | status | retrieval hit | citation hit | s | expected | cited |
|---|---|---|---|---|---|---|---|
| h01 | True | answered | True | True | 6.85 | 2.101 | 2.101, 52.212-3, 12.102, 52.219-9 |
| h02 | True | answered | True | True | 3.8 | 2.101, 15.404-1 | 2.101, 15.404-1 |
| h03 | True | answered | True | True | 3.37 | 16.603-2, 16.603-3 | 18.112, 16.603-2, 16.603-3 |
| h04 | True | partial | False | False | 6.51 | 16.301-3 | 16.405, 36.215, 16.303, 52.246-8, 52.246-5, 52.246-3, 52.243-2, 28.307 |
| h05 | True | answered | True | True | 2.53 | 4.805 | 4.805, 4.801 |
| h06 | True | answered | True | True | 5.18 | 28.102-1 | 28.102-1, 52.228-15, 28.102-3 |
| h07 | True | answered | True | True | 2.8 | 16.504 | 16.504, 52.216-22, 16.501-2 |
| h08 | True | answered | True | True | 4.03 | 37.104 | 2.101, 37.104, 37.103 |
| h09 | True | answered | True | True | 4.11 | 6.401 | 6.401, 6.102 |
| h10 | True | answered | True | True | 3.41 | 42.1502 | 42.1502, 8.406-7 |
| h11 | False | not_found | None | None | 2.35 |  |  |
| h12 | False | not_found | None | None | 1.79 |  |  |
