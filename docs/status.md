# Status & Decisions Log

Update at the end of every session: what changed, what's next, any decision and why.

## Current status (2026-11-14)
- [x] Azure account created
- [x] Budget alert ($30/mo) set (step 0; alerts Owners at 80% actual, 100% forecast)
- [x] Resource providers registered (step 0)
- [x] Infra steps 0-8 run with --debug and recorded in docs/design/00-infra.md (Postgres, ACR, Container Apps deferred)
- [x] Repo skeleton + /health + /smoke (local; 4 unit tests pass; /smoke green against Azure: cold 3.6 s, warm 0.8 s)
- [x] First deploy to Container Apps; /smoke green on live URL (app-level Entra JWT auth; express env)
- [x] FAR ingestion: 4,065 clause-aware chunks in `far-chunks-v1` (17.49 MB of 50 MB), incremental re-run embeds 0
- [x] `POST /ask` live behind Entra auth; App Insights traces via MI + Entra; golden-set baseline: retrieval hit@8 16/19, correct IDK 6/6, false IDK 0/19
- [x] Retrieval tuning (design 05): held-out hit@8 7/10 → 9/10, false IDK 1/10 → 0/10; live on `far-chunks-v2` + vector weight 3
- [x] Award data (design 06): FY2025 Air Force contracts in Postgres (105,408 transactions, 56,832 awards); app reads as MI, read-only; live `/smoke` 6/6
- [x] Public repo: https://github.com/AdityaMogare/contract-copilot
- [x] Text-to-SQL (design 07): `POST /awards/query` live; SQL eval 54/60 runs correct (low effort), 15/15 not-answerable, 18/18 adversarial safe
- [x] Agent (design 08): `POST /chat` with memory, rule-based competition check, human review queue; agent eval 32/34 (low), 0 invented PIIDs, 0 verdicts

## Decisions
| Date | Decision | Why |
|---|---|---|
| 2026-11-14 | Parse FAR from structured HTML/XML, not Document Intelligence | Exact hierarchy, no OCR errors; DI reserved for contract uploads |
| 2026-11-14 | Start AI Search on Free tier | Semantic ranker needs Basic (~$74/mo) > budget; index is rebuildable |
| 2026-11-14 | Managed identity + DefaultAzureCredential, no keys | Same code locally and in Azure; secrets only in Key Vault |
| 2026-11-14 | Compliance feature = gap flagging + human review, not verdicts | USAspending lacks J&A docs; responsible-AI framing |
| 2026-11-14 | Use "Azure for Students" subscription, not PAYG | Spending limit On is a hard cap; a budget only alerts. Revisit if AI Services model/quota is blocked |
| 2026-11-14 | Defer Postgres, ACR, Container Apps until needed | They bill while idle (~$20/mo together); create at /smoke and first deploy |
| 2026-11-14 | Resources in canadacentral, not eastus2 | Students subscription policy allows only 5 regions; canadacentral is closest to the US and has gpt-4.1-mini + text-embedding-3-small (GlobalStandard). RG left in eastus2 (metadata only) |
| 2026-11-14 | `chat` = gpt-5-mini; AI Services account in francecentral | Students sub has 0 quota for gpt-4.1-mini/gpt-4o-mini in all allowed regions; gpt-5-mini has 500K TPM GlobalStandard in francecentral. Cost: ~80-100 ms cross-region per LLM call. gpt-5-mini is a reasoning model (no temperature; reasoning tokens billed) |
| 2026-11-14 | Deploy behind Entra sign-in (Easy Auth, assignment required), not IP restriction | Public URL spends tokens on our credit; Entra matches context.md's architecture and is the stronger interview story. Trade-off: only Aditya can sign in, so demos are done by him or by video |
| 2026-11-14 | Entra JWT validation in FastAPI instead of Easy Auth | Our ACA environment is 'express', which rejects Easy Auth. App-level validation works on any host and needs no secret |
| 2026-11-14 | App MI gets Reader on Search (in addition to Index Data Reader) | Listing index definitions is a control-plane action in Search |
| 2026-11-14 | FAR from eCFR versioner API, fetched per part; 512-dim embeddings | `?chapter=1` is ignored; 512 dims keeps the Free-tier index at 35% of 50 MB |
| 2026-11-14 | `embed` capacity 50K → 300K TPM | Per-token billing, so capacity is free; full ingest 27+ min → ~6 min |
| 2026-11-14 | Model cites by source number; server maps to citations | Citations can't be invented; validated in code |
| 2026-11-14 | App Insights local auth off; MI + me get Monitoring Metrics Publisher | No keys: the connection string can't write telemetry by itself |
| 2026-11-14 | App queries alias `far-chunks`; ingestion writes `far-chunks-v1` | Index rebuilds become an alias swap, not a redeploy |
| 2026-11-14 | Tuning judged on a sealed held-out set; "after" config pre-registered | Avoid reporting numbers tuned on the questions they're measured on |
| 2026-11-14 | One chunk per definition; hybrid with vector weight 3 (not vector-only) | E2 fixed definition misses; dev set doesn't test exact identifiers, which BM25 covers |
| 2026-11-14 | Postgres B1ms, Entra-only auth, public endpoint gated by allow-azure + my IP | Express ACA env has no outbound IPs/VNet; no passwords exist to attack. Stop when idle (`setup.sh 9z`) |
| 2026-11-14 | Read-only + timeout on the MI's login role and per session | Postgres doesn't apply group-role settings to members |
| 2026-11-14 | Public GitHub repo; personal identifiers removed from tracked files, history kept | Portfolio + Week 3 CI needs GitHub; rewriting history would break SHA image tags |
| 2026-11-15 | Text-to-SQL: 4 independent layers (prompt, whole-tree sqlglot allowlist, read-only txn as copilot_reader + 5 s, DB role) | Each alone stops a write; drills showed the timeout is the only layer that stops valid-but-expensive SQL |
| 2026-11-15 | SQL reasoning_effort low, not minimal | Eval: 54/60 vs 46/60; the 6-question probe pointed the other way |
| 2026-11-15 | Competition check = deterministic FAR-cited rules → review items; LLM only explains | Auditable, testable, never a legal verdict |
| 2026-11-15 | One tool-calling agent with call (6) and time (30 s) budgets + forced final step | Probe: loops, empty answers at the cap; a 6-call turn hit the 45 s deadline |
| 2026-11-15 | Memory + review queue in schema `agent`, second pool, same MI | Privileges keep award data unwritable; a second identity is the production answer |

## Next session
- 00-infra still open (deferred by choice, 2026-11-14): own-words Observed column, 30-second explanation, break-it drill, 3 quiz answers
- 01-skeleton open items: break-it drills, quiz, 30-second explanation
- 02 open: cold-start measurement, logs → Log Analytics, break-it, quiz
- 03 open: break-it drills (1536-dim query, remove index-write role), quiz, 30-second explanation
- 04 open: Aditya reviews golden set; break-it drills (throttle chat, DFARS question, prompt injection); quiz; 30-second explanation
- 05 open: decide u03 label (AFFARS question answered as grounded `partial`); delete `far-chunks-v1` once v2 is trusted (needs OK); quiz
- 06 open: quiz; drill "remove the MI principal"; decide whether to add FY2024
- 07 open: SQL prompt tuning needs a held-out SQL set first (NULL handling, total-vs-breakdown); quiz
- 08 open: content-filter → `blocked` also for /ask and /awards/query; latency (4 sequential LLM calls ≈ 14.7 s): try merging the 'done' step with the final answer; Postgres stop/resume drill; quiz
- Next: 10 guardrails (Content Safety prompt shields, PII masking, audit log) or 12 CI/CD eval gate
