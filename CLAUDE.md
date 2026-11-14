# Contract Intelligence Copilot

Full project context, architecture and plan: @docs/context.md
Current status and decisions log: @docs/status.md

## Who you're working with
Aditya is building this to learn Azure end to end for an AI Developer (Senior) interview.
Shipping fast matters, but **him understanding every hop matters more**. Optimize for both.

## The build loop (follow it for every feature)
1. **Design first.** Before writing code for a new feature, check `docs/design/<NN-feature>.md`.
   If it doesn't exist, STOP and ask Aditya to draft it (or draft it *with* him by asking
   questions). Do not write the design for him unprompted. Template: `docs/design/_template.md`.
2. **Build to the design.** Treat the design doc as the spec. If you need to deviate,
   say so and explain why before doing it.
3. **Trace.** After each feature works, show the real HTTP calls (SDK debug logging,
   `az ... --debug`, App Insights spans). Help him update the design doc's Data Flow
   section where reality differed from his prediction.
4. **Break it.** Suggest 2-3 failure injections for the feature; log results in
   `docs/debugging-log.md` (symptom → where it showed up → root cause → fix).
5. **Quiz.** End each feature by asking him 3 interview-style questions about it
   (why this choice, what fails at 10x, what's the auth path). Don't answer them for him.

## Explaining as you go
- When you create an Azure resource, name the ARM call it makes and who can access it.
- When you add an API call, state: method + URL shape, auth (which token, which scope),
  payload shape, and failure modes.
- Prefer small, reviewable commits. One concept per commit. Commit messages explain *why*.

## Engineering rules
- Python 3.12, `uv`, FastAPI, Pydantic v2, `pydantic-settings` for config.
- Auth via `DefaultAzureCredential` everywhere. **No API keys or secrets in code or `.env`
  committed to git.** Secrets live in Key Vault.
- Reference model **deployment names** (`chat`, `embed`) from config, never model names.
- Every external call gets an OpenTelemetry span (from Day 4 onward).
- Text-to-SQL: read-only DB role, sqlglot allowlist (SELECT only, approved tables),
  statement timeout, row limit. Never execute unvalidated SQL.
- Tests decide what ships: `uv run pytest` must pass before a feature is "done".
- Infra changes go in `infra/` (setup.sh now, Bicep later). Never create Azure resources
  that aren't recorded there.
- Watch cost: Azure budget is ~$30/month. Flag anything that costs money before creating it.

## Don'ts
- Don't invent eval numbers or benchmark results. Only report what was measured.
- Don't skip the design step to "save time" even if asked mid-flow; remind him once, then
  follow his call.
- Don't run destructive Azure commands (`az group delete`, resource deletes) without asking.
