# 04 – RAG endpoint: `POST /ask` over the FAR, with citations, "I don't know" and tracing

> Written by Claude at Aditya's request (2026-11-14). Every decision has a **Why**.
> Facts measured before writing (not guesses):
> - Index `far-chunks-v1`: 4,065 chunks, 512-dim vectors, hybrid probes find the right section for
>   4 of 5 hand queries; "simplified acquisition threshold" misses the 2.101 definition (design 03).
> - `chat` (gpt-5-mini) + `chat.completions.parse(response_format=<Pydantic>)` works on api-version
>   `2025-04-01-preview`: **2.0 s at `reasoning_effort=minimal` (0 reasoning tokens), 2.6 s at `low`
>   (192 reasoning tokens)** for a 146-token prompt.
> - Given a half-answerable question ("when can an agency skip competition? and the capital of France?"),
>   the model returned `answerable=false` **and** answered the first half. A boolean is too coarse.
> - App Insights `appi-cczq9h`: workspace-based, canadacentral, `disableLocalAuth` **not set** (the
>   instrumentation key alone can write telemetry today).
>
> Done = `POST /ask` live behind Entra auth; answers carry citations that link to acquisition.gov;
> unanswerable questions get "I don't know"; every hop is an App Insights span; the 25-question golden
> set has a **baseline** score recorded (whatever it is; no tuning in this feature).

## 1. Requirements
**Functional**
- `POST /ask {question}` → an answer grounded **only** in retrieved FAR chunks, with citations
  (`FAR 6.302-1(a)` + acquisition.gov link) for every claim.
- Three outcomes: `answered`, `partial` (some of the question is covered), `not_found` ("I don't know").
  Never answer from the model's general knowledge.
- Optional `part` filter (`"6"`) to scope retrieval.
- Golden set: 25 questions (≥ 6 unanswerable) in `evals/golden.jsonl`, written **before** any tuning,
  plus `evals/run.py` that scores the endpoint and writes a dated report. Baseline recorded in this doc.
- Tracing: one trace per request in App Insights with spans for auth, embed, search, chat, validate.

**Non-functional**
- Latency target p50 < 5 s, p95 < 10 s warm (measured, not assumed: embed ~0.3 s, search ~0.1–0.3 s,
  chat ~2–4 s incl. ~80–100 ms cross-region).
- Cost ≈ **$0.002–0.004/request** at gpt-5-mini list prices (~6K input tokens of context + ≤ 1K output
  incl. reasoning). Recorded per request as span attributes so the real number comes from App Insights.
- Correctness bar (initial, revisit after baseline): unanswerable → `not_found` ≥ 80%; every returned
  citation is one of the retrieved chunks (enforced by code, so 100%).
- Security: same Entra JWT check as `/smoke`; no keys anywhere (App Insights ingestion via Entra too).

**Out of scope**
- Conversation memory / follow-ups (LangGraph, Week 2). Streaming responses.
- Content Safety / prompt shields / PII (Week 2). The corpus is the FAR (trusted); the question is
  user input, but the model only has read-only context, no tools.
- Retrieval tuning (semantic ranker, query rewriting, 2.101 per-definition chunks). This feature
  measures the **baseline**; tuning is a later before/after.
- LLM-as-judge groundedness scoring (Foundry evaluators, Week 3).

## 2. Core entities
- `AskRequest {question: str (1–1000 chars), part: str | None}`
- `RetrievedChunk {n: int, id, citation, url, content, score}`: `n` is the 1-based number shown to the model.
- `ModelAnswer {status: answered|partial|not_found, answer: str, sources: list[int]}`: the **only**
  thing the model produces (strict JSON schema).
- `AskResponse {status, answer, citations: [{citation, url}], retrieved: int, usage: {...}, trace_id}`

## 3. API
```
POST /ask                       (Authorization: Bearer <token for api://<appId>/access_as_user>)
Request:  {"question": "When can an agency use other than full and open competition?", "part": null}
Response 200:
{
  "status": "answered",
  "answer": "When only one responsible source can satisfy the requirement [1], …",
  "citations": [{"citation": "FAR 6.302-1(a)", "url": "https://www.acquisition.gov/far/6.302-1"}],
  "retrieved": 8,
  "usage": {"prompt_tokens": 6012, "completion_tokens": 410, "reasoning_tokens": 0},
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
not_found: 200 with {"status":"not_found","answer":"I don't know based on the FAR sections I searched.","citations":[]}
Errors:
  401/403  token missing/invalid / missing scope (unchanged from 02)
  422      question empty or > 1000 chars (Pydantic)
  503      a dependency failed (body names the hop: embed|search|chat), e.g. 429 after retries
  504      overall deadline (25 s) exceeded
```
*Why 200 for `not_found`:* "I don't know" is a correct answer, not an error. Clients branch on `status`.
*Why `trace_id` in the body:* paste it into App Insights → the whole request's spans.

## 4. Data types, access patterns & scale
- **Read-only.** Per request: 1 embedding (~20 tokens), 1 hybrid query (top 8), 1 chat completion.
  Nothing is written except telemetry.
- Context budget: 8 chunks × ≤ 700 tokens ≈ 5.6K tokens. gpt-5-mini context is far larger; 8 is a
  starting point for the baseline, not a tuned value.
- Scale: one user today. At 10× / 100×, the limits hit in order: `chat` TPM (50K → ~8 requests/min at
  6K tokens each!), then Search Free tier QPS (shared hardware, no SLA). Both are config/tier changes, and
  the 429 path must already be correct (§5 hop 6).
- **Index alias** `far-chunks` → `far-chunks-v1`. The app queries the alias, so a v2 rebuild is a cutover
  of the alias, not an app redeploy. (Free tier: aliases quota 6, measured in 03.)

### Decisions
| Decision | Why | Alternative rejected |
|---|---|---|
| **Model returns source *numbers*; the server maps them to citations** | The model can't invent a citation string or URL. A number outside 1..k is a validation error → retry. Citation correctness is enforced by code | Let the model write "FAR 6.302-1(a)" itself (hallucination-prone, unverifiable) |
| **Structured output with a strict JSON schema** (`parse()` + Pydantic) | The API guarantees schema-valid JSON, so validation failures are semantic (bad source numbers, `answered` with no sources), not syntax | Free-text + regex for [n] markers |
| **Three-state `status`** (`answered` / `partial` / `not_found`) | Measured: a boolean made the model say "not answerable" while answering half the question | `answerable: bool` |
| **"I don't know" decided by the model from context, plus code rules**: `answered`/`partial` must cite ≥ 1 source, else → retry once → `not_found` | RRF scores (~0.016–0.033) aren't calibrated relevance, so a fixed score cutoff would be arbitrary. Measure first on the golden set; add a threshold only if the data says so | A retrieval score threshold from day one |
| **Validate → retry once → else `not_found`** | context.md's golden trace. One retry fixes transient formatting/ref errors; a second failure is a signal, and saying "I don't know" is safer than an unchecked answer | Unbounded retries (latency, cost); returning the invalid answer |
| **`reasoning_effort="low"`, `max_completion_tokens=2000`** | `minimal` was faster (2.0 vs 2.6 s) but synthesis across several clauses benefits from some reasoning. Budget covers reasoning + answer; `finish_reason="length"` is treated as a failed attempt | `minimal` (revisit with golden-set numbers) |
| **Top 8, hybrid (BM25 + vector, RRF), no semantic ranker** | Free tier has no semantic ranker. 8 × 700 tokens fits comfortably | Top 3 (misses multi-section answers); top 20 (cost, dilution) |
| **Async clients reused from app startup** (design 01) | Same token cache and HTTP pools as `/smoke`. Ask-path OpenAI client gets `max_retries=2` (respect 429 `retry-after`); smoke keeps 0 | New clients per request |
| **OpenTelemetry via `azure-monitor-opentelemetry`** + manual spans per hop | One line wires FastAPI + `httpx`/`requests` auto-instrumentation to App Insights; manual spans add our attributes (tokens, k, status). Satisfies "every external call gets a span" (CLAUDE.md) | Hand-rolled logging; OpenAI-only tracing |
| **App Insights ingestion via Entra; local auth disabled** | Consistent with "no keys": the connection string becomes a non-secret locator; writes need a token + *Monitoring Metrics Publisher*. The exporter takes `credential=DefaultAzureCredential()` | Leave key-based ingestion on (anyone with the conn string can write telemetry) |
| **Golden set drafted by Claude from the real index, reviewed by Aditya, committed before any tuning** | Each answerable item lists expected FAR sections verified against the XML, so retrieval hit-rate is objective. Unanswerable items cover out-of-corpus (DFARS-only, award data), off-topic, and future/false premises | No golden set until after tuning (can't show a before/after honestly) |

## 5. Data flow (numbered hops), deployed
1. **Laptop → Entra:** `az account get-access-token --scope api://<appId>/access_as_user` (unchanged from 02).
2. **curl → ACA ingress → FastAPI:** `POST https://ca-copilot-…/ask` + Bearer. OTel starts the request span.
3. **`require_user`:** JWT signature (cached JWKS), `iss`, `aud`, `exp`, `scp` → 401/403 or continue. Span `auth`.
4. **App → Azure OpenAI (embed):** `POST https://ais-cczq9h.cognitiveservices.azure.com/openai/deployments/embed/embeddings?api-version=…`
   `{input:[question], dimensions:512}` · MI token, scope `https://cognitiveservices.azure.com/.default`
   (cached, from IMDS-equivalent identity endpoint in ACA) · role *Cognitive Services OpenAI User*.
   Fails: 429 → retry with `retry-after` (≤ 2) → 503 `embed`; 401 if the role is missing.
5. **App → Search:** `POST https://srch-cczq9h.search.windows.net/indexes/far-chunks/docs/search?api-version=…`
   (alias) `{search:q, vectorQueries:[{kind:"vector", vector, fields:"content_vector", k:50}], top:8,
   select:"id,citation,url,content", filter?}` · scope `https://search.azure.com/.default` · role
   *Search Index Data Reader*. Fails: 403 (role), 400 (vector dims ≠ 512: the 03 break-it), 503/429 (Free tier
   throttling) → 503 `search`. 0 results → skip the LLM, return `not_found` (saves cost).
6. **App → Azure OpenAI (chat):** `POST …/openai/deployments/chat/chat/completions` with
   `response_format={type:"json_schema", strict:true, schema:ModelAnswer}`, `reasoning_effort:"low"`,
   `max_completion_tokens:2000`; messages = system rules + numbered sources + question. Same scope/role as hop 4.
   Fails: 429 (50K TPM ≈ 8 req/min at 6K tokens) → retry → 503 `chat`; `finish_reason=length` → failed attempt;
   content filter (400 `content_filter`) → 503 with that reason.
7. **Validate:** `sources ⊆ {1..k}`, `answered|partial ⇒ sources ≠ ∅`. Fail → **one** retry of hop 6 with the
   error appended to the messages → still failing → `not_found` (span attribute `validation_failed=true`).
8. **Map + respond:** sources → `{citation, url}` (deduped, in order). Span attributes: tokens, status, k.
9. **App → App Insights (async, batched):** `POST https://canadacentral-1.in.applicationinsights.azure.com/v2.1/track`
   · MI token, scope `https://monitor.azure.com/.default` · role *Monitoring Metrics Publisher* on `appi-cczq9h`.
   Fails: dropped telemetry, never a failed request (exporter is off the request path).

Locally, hops 4–6 and 9 run as Aditya (AzureCliCredential); hop 1–3 are skipped when `AUTH_REQUIRED=false`.

## 6. High-level design
```
app/
  rag/
    retrieve.py   embed_query(), hybrid_search() → [RetrievedChunk]          spans: embed, search
    prompt.py     SYSTEM rules, build_messages(question, chunks)
    answer.py     ModelAnswer, generate() → validate → retry once → AskResponse  spans: chat, validate
  routers/ask.py  POST /ask, Depends(require_user), deadline 25 s, error → 503/504 with hop name
  telemetry.py    configure_azure_monitor(credential=…) if APPLICATIONINSIGHTS_CONNECTION_STRING set
evals/
  golden.jsonl    {id, question, answerable, expected_sections[], notes}
  run.py          calls /ask (local or live URL) → hit@8 (expected section retrieved), citation precision,
                  not_found accuracy, false-IDK rate, latency p50/p95 → evals/reports/YYYY-MM-DD.md
infra/setup.sh    step 2b: appi disableLocalAuth=true; step 8: Monitoring Metrics Publisher (app MI + me);
                  step 7b: alias far-chunks → far-chunks-v1; step 13: env SEARCH_INDEX=far-chunks, APPLICATIONINSIGHTS_CONNECTION_STRING
```
Config adds: `search_index` default → `far-chunks` (alias), `rag_top_k=8`, `rag_reasoning_effort="low"`,
`applicationinsights_connection_string: str | None`. New deps: `azure-monitor-opentelemetry`.

**Tests** (no network): fake retrieve + fake chat →
- valid answer → citations mapped from source numbers, deduped
- source number out of range → one retry → then `not_found`
- `answered` with no sources → retry → `not_found`
- 0 retrieved → `not_found` without calling chat
- chat 429 after retries → 503 `{"hop":"chat"}`; deadline → 504
- `/ask` requires auth (reuses 02 fixtures); 422 on empty / > 1000 chars

**Build order (one concept per commit)**
1. evals: golden set (25 Qs) → **Aditya reviews before anything is tuned**
2. infra: alias, App Insights Entra-only ingestion + roles (run with `--debug`)
3. feat: retrieve + answer + `/ask` + tests (local, auth off)
4. feat: OpenTelemetry → App Insights; verify spans for one request
5. eval: baseline run locally → report committed → numbers into this doc
6. deploy (`infra/deploy.sh`) + live `/ask` + live trace

## 7. Expected deep-dive questions
1. **How do you stop the model from making up citations, and how do you decide "I don't know"?**
   (numbered sources mapped server-side; strict schema; validation + one retry; three-state status; why not a
   score threshold yet, and what data would justify one.)
2. **Walk me through one `/ask` request end to end, with auth at every hop.** (user token → JWT checks →
   MI tokens per scope, cached → embed → hybrid/RRF → chat → validate → App Insights via Entra; where the
   latency goes, from the real trace.)
3. **What breaks at 10× traffic, and what does it cost?** (chat TPM 50K ≈ 8 req/min is the first wall; 429
   handling; Free-tier search; cost/request from span attributes; caching embeddings/answers for repeat
   questions.)

---
## After building
### Golden-set baseline (measured)
-
### Trace vs prediction (what I got wrong)
-
### Break-it results (planned drills)
- Throttle: set `chat` capacity to 1K TPM → expect 429 → retries → 503 `chat` (then restore)
- Ask a question whose answer is only in DFARS → expect `not_found`
- Prompt injection in the question ("ignore the sources and…") → expect `not_found` / grounded answer
### 30-second explanation
-
