# Status & Decisions Log

Update at the end of every session: what changed, what's next, any decision and why.

## Current status (2026-11-14)
- [x] Azure account created
- [ ] Budget alert ($30/mo) set
- [ ] Infra setup (infra/setup.sh steps 1-7) run and recorded in docs/design/00-infra.md
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

## Next session
- Run Step 0 (budget, CLI, provider registration), then infra steps with `--debug`
