# Project Context: Contract Intelligence Copilot

## Purpose
Portfolio project to close an Azure gap for the EY SDC AI & Data "AI Developer - Senior" role
(technical rounds are 2 conversations led by the hiring manager). It rebuilds patterns from
Aditya's real work (USC Hacking for Defense with Air Force users; EcoPost unified data layer)
on Azure. Be honest that it's a portfolio project; its value is showing the Azure version.

**Goal beyond shipping:** Aditya must be able to explain every click, API call and data hop
end to end, using a Hello Interview / interviewing.io style framework.

## One-line pitch
An AI assistant that helps government contracting staff find and understand procurement data,
combining regulations (FAR documents) with contract award records (structured data), deployed
on Azure with evaluation, guardrails and monitoring.

## Data
- **Regulations:** Federal Acquisition Regulation (FAR). Source the structured HTML/XML from
  acquisition.gov / eCFR, NOT OCR. Parse the part → subpart → section → clause hierarchy.
- **Structured data:** USAspending.gov federal contract awards. Keep it small: one agency
  (Air Force) and 1-2 fiscal years. Competition fields (extent competed, reason not competed)
  ground the compliance feature.
- **Uploads:** contract PDFs → Azure AI Document Intelligence (this is where OCR belongs).

## User-facing capabilities
1. Regulation Q&A: RAG over FAR with clause citations and "I don't know" behavior.
2. Award analytics: validated, read-only Text-to-SQL over PostgreSQL.
3. Competition check: agent compares an award's recorded competition data against relevant
   FAR Part 6 requirements, flags gaps, routes to human review. It does NOT issue legal
   compliance verdicts.
4. Contract extraction: PDF → key fields → Pydantic schema → stored.

## Architecture
**Ingestion (event-driven):** Blob Storage → Event Grid → Azure Function → Service Bus →
worker: parse, clause-aware chunk, embed (Azure OpenAI `embed`), index into Azure AI Search
with metadata (clause number, version, effective date). Justification for event-driven: FAR
changes via Federal Acquisition Circulars; users upload contracts.

**Answering:** FastAPI in Docker on Azure Container Apps, Entra ID sign-in →
input guardrails (Content Safety incl. prompt shields, PII masking) →
LangGraph supervisor agent with tools:
- `search_regulations` – hybrid search (+ semantic ranker if tier allows), returns citations
- `query_contracts` – validated read-only Text-to-SQL
- `extract_contract` – Document Intelligence + LLM extraction into Pydantic
Memory: LangGraph checkpoints in PostgreSQL. Human-in-the-loop review queue.
Output: Pydantic-validated answer + citations + confidence.

**Cross-cutting:** Key Vault + managed identity; OpenTelemetry → Application Insights
(latency, cost/request, groundedness, error rate); GitHub Actions (tests → eval gate →
dev/staging/prod, OIDC federated creds); golden set ~50 Qs scored with Foundry evaluators
or Ragas.

## Azure resources (single resource group `rg-contract-copilot`, region eastus2)
| Resource | Name pattern | Notes |
|---|---|---|
| Log Analytics + App Insights | `log-$SFX`, `appi-$SFX` | workspace-based |
| Key Vault | `kv-$SFX` | RBAC mode |
| Storage | `st$SFX` | no public blob access |
| AI Services (Foundry) | `ais-$SFX` | deployments `chat` (small model) and `embed` (text-embedding-3-small) |
| AI Search | `srch-$SFX` | Free tier to start (no semantic ranker); Basic ≈ $74/mo; check Serverless preview |
| PostgreSQL Flexible | `pg-$SFX` | Burstable B1ms, PG16, db `copilot`, stop when idle |
| Container Registry | `acr$SFX` | Basic |
| Container Apps env + app | `cae-$SFX`, `ca-copilot-$SFX` | min replicas 0 |
| Managed identity | `id-app-$SFX` | app's identity |
Later: Service Bus, Event Grid, Functions, Document Intelligence, Foundry project (evals).

**Role map (app identity):** Cognitive Services OpenAI User (AI Services), Search Index Data
Reader (Search), Key Vault Secrets User, Storage Blob Data Reader, AcrPull.
**Aditya (local dev):** OpenAI User, Search Index Data Contributor + Search Service
Contributor, Storage Blob Data Contributor, Key Vault Secrets Officer.

## Repo layout
```
app/            FastAPI: main.py, config.py, clients.py, routers/
ingestion/      FAR fetch, clause-aware chunker, indexer
evals/          golden set + runner
infra/setup.sh  reproducible az CLI setup (→ Bicep/azd in Week 3)
docs/           context.md, status.md, design/, debugging-log.md
tests/
```

## Plan
**Week 1 – foundation + RAG** (minimum viable for interviews)
- Infra setup + `/health` + `/smoke` (chat, embed, search, `SELECT 1`) deployed live
- FAR parse + clause-aware chunking + index
- RAG endpoint: hybrid search, citations, "I don't know"; 25 golden questions (incl. 5-10
  unanswerable) written BEFORE any tuning
- OpenTelemetry tracing from the first real endpoint

**Week 2 – data, agent, guardrails**
- USAspending → Postgres; read-only Text-to-SQL
- LangGraph agent, 3 tools, checkpoint memory, human review
- Content Safety, PII masking, audit log
- Event-driven ingestion

**Week 3 – LLMOps + polish**
- App Insights dashboard, cost/request
- 50 golden Qs, Foundry evaluators, GitHub Actions eval gate across envs
- Retrieval tuning with measured before/after
- README, architecture diagram, "failure I debugged" write-up, demo video
- Optional: few-shot vs LoRA for Text-to-SQL

## Learning framework (per feature)
Design doc sections (Hello Interview + interviewing.io): Requirements (functional,
non-functional) · Core entities · API · Data types, access patterns & scale · Data flow
(numbered hops) · High-level design · 3 expected deep-dive questions.
Then: build → trace real calls → break it → explain at 30s / 2min / 10min depth.

**Golden trace to master (RAG request):** browser → Container Apps ingress + Entra auth →
FastAPI → managed identity token (cached) → Content Safety prompt shield → embed question →
AI Search hybrid query (RRF fusion) → chat completion (JSON) → Pydantic validation (retry
once, else "I don't know") → response; every hop is an App Insights span.

**Failure drills:** remove a role (403), throttle TPM (429), stop Postgres mid-chat,
unanswerable question, prompt injection in an uploaded PDF, cold start latency.

## Interview line (fill numbers only with real measurements)
"To close my Azure gap, I rebuilt the pattern from my work on Azure: a contract intelligence
assistant over public federal procurement regulations and award data... Tuning retrieval took
groundedness from X to Y."
