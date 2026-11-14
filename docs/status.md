# Status & Decisions Log

Update at the end of every session: what changed, what's next, any decision and why.

## Current status (2026-11-14)
- [x] Azure account created
- [x] Budget alert ($30/mo) set (step 0; alerts Owners at 80% actual, 100% forecast)
- [x] Resource providers registered (step 0)
- [x] Infra steps 0-8 run with --debug and recorded in docs/design/00-infra.md (Postgres, ACR, Container Apps deferred)
- [ ] Repo skeleton + /health + /smoke
- [ ] First deploy to Container Apps; /smoke green on live URL

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

## Next session
- 00-infra still open (deferred by choice, 2026-11-14): own-words Observed column, 30-second explanation, break-it drill, 3 quiz answers
- Draft docs/design/01-skeleton.md (/health + /smoke) before any app code
