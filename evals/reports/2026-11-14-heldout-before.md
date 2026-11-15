# Eval: heldout-before (2026-11-14)

Config: index alias `far-chunks-v1`, top_k=8, reasoning_effort=low, vector_weight=1.0, chat=`chat`, embed dims=512. Golden set: `evals/golden.jsonl`.

| Metric | Value |
|---|---|
| questions | 12 |
| errors | 0 |
| retrieval_hit@k (answerable) | 7/10 (70%) |
| answered_or_partial (answerable) | 9/10 (90%) |
| fully_answered (answerable) | 8/10 (80%) |
| citation_hit (answerable, any expected section cited) | 7/10 (70%) |
| false_idk (answerable → not_found) | 1/10 (10%) |
| correct_idk (unanswerable → not_found) | 2/2 (100%) |
| validation_failed | 0 |
| retries (attempts > 1) | 0 |
| latency_p50_s | 3.37 |
| latency_p95_s | 5.98 |
| avg_prompt_tokens | 3719 |
| avg_completion_tokens (incl. reasoning) | 252 |

| id | answerable | status | retrieval hit | citation hit | s | expected | cited |
|---|---|---|---|---|---|---|---|
| h01 | True | not_found | False | False | 4.35 | 2.101 |  |
| h02 | True | answered | True | True | 4.16 | 2.101, 15.404-1 | 2.101, 15.404-1 |
| h03 | True | answered | True | True | 2.81 | 16.603-2, 16.603-3 | 16.603-2, 18.112, 16.603-3 |
| h04 | True | partial | False | False | 5.01 | 16.301-3 | 16.405, 36.215 |
| h05 | True | answered | True | True | 3.08 | 4.805 | 4.805 |
| h06 | True | answered | False | False | 5.98 | 28.102-1 | 28.102-3, 52.228-15, 28.103-3, 28.103-1 |
| h07 | True | answered | True | True | 3.14 | 16.504 | 16.504, 52.216-22 |
| h08 | True | answered | True | True | 5.77 | 37.104 | 37.104 |
| h09 | True | answered | True | True | 3.6 | 6.401 | 6.401, 52.214-10, 14.101 |
| h10 | True | answered | True | True | 3.14 | 42.1502 | 42.1502, 8.406-7 |
| h11 | False | not_found | None | None | 2.23 |  |  |
| h12 | False | not_found | None | None | 1.72 |  |  |
