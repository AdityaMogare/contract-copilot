# 01 – App skeleton: /health + /smoke

> Written by Claude at Aditya's request (2026-11-14), so there are no prior predictions.
> Every decision has a **Why** so it can be read and challenged. Numbers marked *target* are
> goals, not measurements; measured values go in "Trace vs prediction" after building.

## 1. Requirements
**Functional**
- `GET /health` returns 200 if the process is up. It makes **no external calls**.
  *Why:* Container Apps' liveness probe will hit it every few seconds. If it called Azure
  OpenAI, a slow model would get healthy replicas restarted and would cost tokens on every probe.
- `GET /smoke` proves that each dependency is reachable **with the identity the app is
  running as**, using the same clients the real features will use:
  | Check | Call | Proves |
  |---|---|---|
  | `chat` | 1 chat completion on deployment `chat`, tiny prompt | AI Services auth, `chat` deployment, gpt-5-mini params |
  | `embed` | 1 embedding on deployment `embed` | `embed` deployment; vector length = 1536 |
  | `search` | list index names | Search endpoint, Entra auth on Search |
  | `keyvault` | list secret *properties* (never values) | Key Vault data role |
  | `storage` | list blobs in `far-raw` (max 1) | Blob data role, Entra-only storage |
- Checks run **concurrently**, each with its own timeout. One failing check never hides the others.
- Status codes: **200 if every check passes, 503 if any fails.** The body always has per-check detail.
  *Why:* the consumers are a human, and later a CI step after deploy (`curl --fail`). A
  non-2xx code makes CI fail without parsing JSON, and the body says which check broke.
  This only works because probes use `/health`, not `/smoke`.

**Non-functional**
- Latency *target*: `/smoke` p95 < 10 s locally. It's bounded by `chat`: a reasoning model in
  francecentral, called from the US. Per-check timeout: 20 s.
- Cost per `/smoke` call: chat ≈ 20 input + ≤ 64 output tokens with `reasoning_effort: minimal`,
  embed ≈ 5 tokens, so ≪ $0.001.
- Security: no keys anywhere. All five calls use Entra tokens from one `DefaultAzureCredential`.
  The response never includes secret values, tokens or full exception dumps (error type + a short message only).
- `uv run pytest` passes without Azure access (checks are faked in unit tests).

**Out of scope (and why)**
- Postgres `SELECT 1`: the server doesn't exist yet (deferred for cost; step 9).
- Auth on `/smoke` itself: this feature runs locally only. When deployed (feature 02), the app
  sits behind Container Apps Entra sign-in, so `/smoke` isn't anonymous. Until then, don't deploy it.
- OpenTelemetry spans: CLAUDE.md requires them from Day 4. Adding them here would double the
  surface of the first feature. For now, the SDKs' HTTP debug logging is the trace.
- Retries: smoke checks report the *first* result. Retrying would hide the 401s and 429s we want to see.

## 2. Core entities
- `Settings`: typed config (pydantic-settings), loaded once.
- One `DefaultAzureCredential` (async) shared by every client, created at startup and closed at shutdown.
- `Clients`: AsyncAzureOpenAI, SearchIndexClient, SecretClient, BlobServiceClient.
- `CheckResult {name, ok, ms, detail | error}` and `SmokeReport {ok, checks[]}`.

## 3. API
```
GET /health
Response 200: {"status": "ok"}

GET /smoke
Response 200 (all ok) / 503 (any failed), same shape:
{
  "ok": false,
  "checks": [
    {"name": "chat",     "ok": true,  "ms": 1840, "detail": "model=gpt-5-mini-2025-08-07"},
    {"name": "embed",    "ok": true,  "ms": 310,  "detail": "dims=1536"},
    {"name": "search",   "ok": true,  "ms": 220,  "detail": "indexes=0"},
    {"name": "keyvault", "ok": true,  "ms": 190,  "detail": "secrets=0"},
    {"name": "storage",  "ok": false, "ms": 150,
     "error": "HttpResponseError 403: AuthorizationPermissionMismatch"}
  ]
}
Errors: a check's error string is "<ExceptionType> <http status if any>: <short code/message>"
        or "timeout after 20s". /smoke itself does not raise 500 for a failed check.
```

## 4. Data types, access patterns & scale
- Read-only: nothing is written anywhere. Callers: a human, a few times a day; CI, once per deploy.
- 1000× /smoke: 1000 chat calls ≈ 84K tokens, well over the 50K TPM `chat` quota, so expect
  **429s**, and those would show up in `/smoke` as failures. That's another reason it must not be public.

## 5. Data flow (numbered hops) – `embed` check, local run
1. **curl → FastAPI** `GET http://localhost:8000/smoke`. No auth (local only).
2. **`/smoke` → `check_embed()`** runs under `asyncio.wait_for(…, 20 s)` alongside the other 4 checks.
3. **AsyncAzureOpenAI → token provider**: before sending, the SDK calls
   `get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")`.
4. **DefaultAzureCredential → credential chain**, tried in order: Environment → WorkloadIdentity →
   ManagedIdentity → … → **AzureCliCredential**. Locally the chain gets as far as the CLI, which runs
   `az account get-access-token --scope https://cognitiveservices.azure.com/.default`, so the token is
   **mine** (my USC Entra account, MFA). In Container Apps, **ManagedIdentityCredential** wins and
   calls the platform's identity endpoint, using `AZURE_CLIENT_ID` to pick `id-app-cczq9h`.
   The token is **cached in memory per scope** inside the credential and refreshed ~5 min
   before expiry, so only the first call per scope pays this hop.
   *Failure:* not logged in → `CredentialUnavailableError` → check fails with "auth".
5. **SDK → AI Services** `POST https://ais-cczq9h.cognitiveservices.azure.com/openai/deployments/embed/embeddings?api-version=2025-04-01-preview`,
   header `Authorization: Bearer <token>`, body `{"input": "smoke test"}`.
   *Failures:* 401 `PermissionDenied` (role missing, or still propagating: we saw ~8 min),
   429 (TPM exhausted, `retry-after` header), timeout (cross-region, or service slow).
6. **AI Services → RBAC check**: the token's `oid` must hold a role with the
   `…/OpenAI/deployments/embeddings/action` data action on `ais-cczq9h` (Cognitive Services OpenAI User).
7. **Response** `200 {"data":[{"embedding":[1536 floats]}], "usage":{…}}`, so the check records `dims=1536`.
8. **FastAPI → curl**: aggregate the 5 results, 200 or 503.

Other checks differ only at hops 3–6: Search uses scope `https://search.azure.com/.default` →
`GET https://srch-cczq9h.search.windows.net/indexes`; Key Vault uses `https://vault.azure.net/.default` →
`GET https://kv-cczq9h.vault.azure.net/secrets` (first a 401 challenge, then retried with a token);
Storage uses `https://storage.azure.com/.default` → `GET https://stcczq9h.blob.core.windows.net/far-raw?restype=container&comp=list`.

## 6. High-level design
```
app/
  main.py     FastAPI app; lifespan creates/closes credential + clients; mounts routers
  config.py   Settings (pydantic-settings), reads env / .env
  clients.py  build_clients(settings, credential) -> Clients; close_clients()
  routers/
    health.py  GET /health
    smoke.py   GET /smoke  → runs CHECKS concurrently → SmokeReport
  smoke_checks.py  check_chat/embed/search/keyvault/storage(clients, settings) -> str detail
tests/  test_health.py, test_smoke.py (fake checks, no Azure)
```
*Why one shared credential + clients created in lifespan:* creating a credential per request
throws away its token cache (one extra az CLI / identity call per request) and leaks HTTP sessions.

**Config** (env vars; `.env` locally, gitignored; `.env.example` committed). None are secrets.
| Setting | Local value | In Azure (feature 02) |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | `https://ais-cczq9h.cognitiveservices.azure.com/` | Container App env var |
| `AZURE_OPENAI_API_VERSION` | `2025-04-01-preview` | same |
| `CHAT_DEPLOYMENT` / `EMBED_DEPLOYMENT` | `chat` / `embed` | same |
| `SEARCH_ENDPOINT` | `https://srch-cczq9h.search.windows.net` | env var |
| `KEY_VAULT_URL` | `https://kv-cczq9h.vault.azure.net/` | env var |
| `STORAGE_ACCOUNT_URL` / `STORAGE_CONTAINER` | `https://stcczq9h.blob.core.windows.net` / `far-raw` | env var |
| `AZURE_CLIENT_ID` | *unset* (so the CLI credential is used) | clientId of `id-app-cczq9h` |
| `SMOKE_TIMEOUT_S` | `20` | `20` |

*Why `2025-04-01-preview`:* gpt-5-mini needs `max_completion_tokens` / `reasoning_effort`, which
the older GA version (2024-10-21) rejects. This is the version our curl test returned 200 with. One version for both deployments keeps config simple.
*Why the chat check uses `reasoning_effort: "minimal"` and `max_completion_tokens: 64`:* reasoning tokens
are billed as output. Minimal effort keeps the check fast and cheap. Too low a cap could come back
with empty content, so the check passes on HTTP 200 + `finish_reason`, not on the text.

## 7. Expected deep-dive questions
1. Why does the liveness probe use `/health` and not `/smoke`? What happens if you swap them during a model outage?
2. Locally the token is yours; in Azure it's the managed identity's. How does the same code pick
   the right one, and what's the risk if `AZURE_CLIENT_ID` is missing when the host has two identities?
3. `/smoke` returns 503 for one check failing on a 401 right after deploy. How do you tell
   "role missing" from "role still propagating", and what should CI do about it?

---
## After building
### Trace vs prediction (what I got wrong)
Measured 2026-11-14, local run (macOS → canadacentral / francecentral), `az login` user with MFA.
| | Design said | Measured |
|---|---|---|
| `/smoke` latency | *target* p95 < 10 s | **Cold 3.58 s, warm 0.83 s** (one sample each, not a p95) |
| Per check, warm | chat is the slowest | chat 826 ms (gpt-5-mini, francecentral) · embed 329 · keyvault 278 · search 96 · storage 86 ms |
| Per check, cold | not predicted | Every check ≈ +2 s. The token cache was empty, so each check walked the credential chain at the same time |
| Credential chain locally | ends at AzureCliCredential | Confirmed: `EnvironmentCredential` "No environment configuration found" → `ManagedIdentityCredential` **probed IMDS** `GET http://169.254.169.254/metadata/identity/oauth2/token` (no such endpoint on a laptop, so it fails) → `DefaultAzureCredential acquired a token from AzureCliCredential`. The IMDS probe and the `az` subprocess are the cold-start cost. |
| Token caching | cached per scope in the credential | Confirmed: a second embed call logged no identity activity |
| Key Vault hop | 401 challenge, then retry with a token | Confirmed: `GET /secrets?api-version=2026-04-01` → **401** + `WWW-Authenticate: Bearer authorization=".../9ddaaca1-…", resource="https://vault.azure.net"` → token from the CLI → retry. The SDK used api-version **2026-04-01**, while the CLI in step 3 used **7.4**: same REST API, different client pinning. |
| chat params | `max_completion_tokens: 64` + `reasoning_effort: minimal` might return empty text | `finish_reason=stop`: 64 tokens were enough |
| Response's `model` | deployment name `chat` | `gpt-5-mini-2025-08-07`: the response reports the *model*, even though the request named the *deployment* |

Follow-ups (not done): cold start could drop ~1–2 s by excluding ManagedIdentityCredential when
running locally, or by warming tokens in `lifespan`. Only worth it if cold latency matters in Azure (min replicas = 0).
### Break-it results
-
### 30-second explanation
-
