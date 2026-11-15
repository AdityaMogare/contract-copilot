# Debugging Log

Format: symptom → where it showed up → root cause → fix.

## 2026-11-14 – `az storage account check-name` → `SubscriptionNotFound`
- **Symptom:** `(SubscriptionNotFound) Subscription aa6c…cdeb was not found`, even though the subscription exists and I'm Owner.
- **Where:** az CLI stderr, during a name-availability check before step 0.
- **Root cause:** `Microsoft.Storage` wasn't registered on the subscription; ARM gives a misleading error for unregistered namespaces.
- **Fix:** `az provider register --namespace Microsoft.Storage` (step 0). It's async: POST /register returns 200, then poll until `Registered`.

## 2026-11-14 – Budget PUT → 401 `RequestDisallowedByAzure`
- **Symptom:** `Resource 'budget-contract-copilot' was disallowed by Azure ... without authenticating through MFA`.
- **Where:** `infra/logs/00-budget.log`, response to `PUT .../Microsoft.Consumption/budgets/...`.
- **Root cause:** Azure mandatory MFA for ARM write operations. The `az login` token had no MFA claim. ARM sent `WWW-Authenticate: error="insufficient_claims"` asking for `acrs=p1`. (Provider-register POSTs were not blocked.)
- **Fix:** `az logout` (to wipe the cached password-only access token), then
  `az login --use-device-code --scope https://management.core.windows.net//.default --claims-challenge <base64 from WWW-Authenticate>`,
  approve MFA. Verify with the token's `amr` claim: `["pwd","mfa"]`. Budget PUT → 201.
- **Gotchas on the way:** (1) re-login *without* logout still used the cached 09:25 `pwd`-only
  access token, so the call stayed at 401; (2) `AADSTS700171` = clicked Cancel on the device-code
  "Are you trying to sign in to Azure CLI?" page.

## 2026-11-14 – Log Analytics PUT → 403 `RequestDisallowedByAzure` (region)
- **Symptom:** `Resource 'log-cczq9h' was disallowed by Azure: This policy maintains a set of best available regions...`
- **Where:** `infra/logs/02-log-403-eastus2.log`, response to the workspace PUT. Note: same error *code* as the MFA block, different cause, so read the message.
- **Root cause:** the Azure for Students subscription has the Azure Policy assignment "Allowed resource deployment regions":
  belgiumcentral, canadacentral, denmarkeast, francecentral, norwayeast. eastus2 is not allowed. (Resource groups weren't blocked.)
  Found with `az policy assignment list --disable-scope-strict-match`.
- **Fix:** `LOCATION=canadacentral` in `infra/setup.sh` (closest to the US; checked that gpt-4.1-mini and text-embedding-3-small are GlobalStandard there). RG stays in eastus2 (metadata only).

## 2026-11-14 – Embeddings 401 `PermissionDenied` for ~8 min after role assignment
- **Symptom:** `POST /openai/deployments/embed/embeddings` → 401 "Principal does not have access to API/Operation.", while `POST /openai/deployments/chat/chat/completions` with the *same token* → 200.
- **Where:** curl against `https://ais-cczq9h.cognitiveservices.azure.com` right after step 8 (role PUT returned 201 at ~11:14).
- **Root cause:** RBAC propagation is eventually consistent and cached per data-plane front end/operation. The role assignment was correct (verified with `az role assignment list --scope <ais id>`). Key Vault and Storage picked it up in under 1 min; embeddings took ~8 min (200 at 11:22).
- **Fix:** none needed, just wait. Lessons: (1) in deploy pipelines, retry with backoff after granting roles; (2) a 401/403 right after a role change is not proof the role is wrong; check the assignment exists first, then wait.

## 2026-11-14 – Container Apps env PUT → 400 `ExpressAzureMonitorLogDestNotSupported`
- **Symptom:** "Azure Monitor Log Destination is not supported for environment 'cae-cczq9h' on express environments."
- **Where:** `infra/logs/11-cae-400-azure-monitor.log`, response to `PUT …/Microsoft.App/managedEnvironments/cae-cczq9h`, body `appLogsConfiguration.destination: azure-monitor`.
- **Root cause:** the platform created this as an "express" environment (decided server-side; nothing in the request or in `az containerapp env show` marks it as express), and express environments reject the azure-monitor destination. The error's doc link (aka.ms/aca/express) redirects to the portal, not to docs.
- **Fix:** `--logs-destination none`, plus a diagnostic setting (`allLogs` → log-cczq9h) → PUT 200. **Open:** confirm logs actually arrive in the workspace once the app runs.

## 2026-11-14 – Easy Auth PUT → 400 `ExpressAuthConfigNotSupported` (app briefly public without sign-in)
- **Symptom:** "Authentication (EasyAuth) is not supported for container app 'ca-copilot-cczq9h' on express environments."
- **Where:** `infra/logs/13-auth.log`, `PUT …/containerApps/ca-copilot-cczq9h/authConfigs/current` → 400.
- **Root cause:** same platform behaviour as step 11: our environment is "express", and express environments reject Easy Auth. The design assumed Easy Auth was available. The ordering in step 13 (create the app with external ingress → then add auth) meant that when auth failed, **the app was left public with no sign-in**.
- **Containment:** `az containerapp ingress disable` a few minutes after create → public URL now 404.
- **Lesson:** never create a public endpoint and add its protection in a later step. Create it with ingress off, attach protection, *then* open ingress, so a failure leaves it closed.
- **Fix:** pending a design decision (app-level Entra auth in FastAPI / IP restriction / non-express env).

## 2026-11-14 – Live /smoke: search 403 for the managed identity (passed locally)
- **Symptom:** `search ok=False HttpResponseError 403 Forbidden` on the deployed app; the other 4 checks green. The same code passed locally.
- **Where:** live `/smoke` response, called with our API token.
- **Root cause:** locally the call ran as *me* (Owner → has `Microsoft.Search/searchServices/indexes/read`). In Azure it runs as `id-app-cczq9h`, which only had *Search Index Data Reader* (document dataActions). Listing index definitions is a control-plane action in Search (the step 7 finding). **"Works on my machine" = works with my identity.**
- **Fix:** step 8 adds *Reader* on the search service for the app MI (read-only; can't list admin keys). Green at the next call.
- **Lesson:** test the app as its own identity before deploying (e.g. a local run with a service principal or a token for the MI). Owner hides missing roles.

## 2026-11-14 – Public URL 502 "App is not available" for ~4.5 min after enabling ingress
- **Symptom:** every path → 502 `{"error":"App is not available"}`; replica Running + Ready; console logs showed only probe requests from 127.0.0.1.
- **Root cause:** ingress config propagation on the (express) environment. `revision restart` isn't supported on express (400). It resolved itself at ~4.5 min.
- **Fix:** wait. In a pipeline: poll `/health` with backoff for several minutes after an ingress change before declaring failure.

## 2026-11-14 – Open: Container Apps logs not arriving in Log Analytics
- Diagnostic setting `allLogs` → `log-cczq9h` exists (PUT 200), environment `appLogsConfiguration.destination = none` (express rejects azure-monitor). After ~10 min of traffic: `search * | where TimeGenerated > ago(3h)` returns **0 rows**. `az containerapp logs show` (live stream) works. Next: check again later (ingestion delay), then try `log-analytics` destination with the shared key stored in Key Vault, or rely on App Insights via OpenTelemetry (planned anyway).

## 2026-11-14 – Search stats stuck at 37 docs after indexing 716
- **Symptom:** `GET /indexes/far-chunks-v1/stats` and `/servicestats` reported 37 docs / 170 KB minutes after a run that wrote 716 docs (200 OK on every batch). `search *` with `$count` showed 716 immediately.
- **Root cause:** statistics are computed asynchronously; queries see new docs right away, stats lag (here ~3 min).
- **Fix:** poll stats until `documentCount` matches before using them for the sizing gate.

## 2026-11-14 – Citation `FAR 52.212-4(v)–(a)` + hash that ignored metadata
- **Symptom:** a probe returned a backwards paragraph range.
- **Where:** `ingestion.probe "time-and-materials … commercial products"`, result #5.
- **Root cause:** (1) clause Alternates restart paragraph labels at (a), and `_range` assumed one ascending run; (2) fixing it would not have reached the index because `content_hash` covered only `content`, so the changed citation looked "unchanged".
- **Fix:** ranges rendered per run (`(v); (a)–(b)`); hash covers all written metadata. Tests for both. One full re-embed (~$0.03).
- **Lesson:** an incremental-update key must cover *everything you write*, not just the expensive part.

## 2026-11-14 – "Successful" full re-ingest that silently skipped Parts 52–53
- **Symptom:** report said 4,025 chunks (expected 4,065), embedded + unchanged = 2,940 (≠ chunks), exit code 0. `FAR 52.212-4(v)–(a)` still in the index after the fix.
- **Where:** `uv run python -m ingestion.run … 2>&1 | tail -12` output.
- **Root cause:** the run crashed inside Part 52 (after chunking, before writing; Part 53 never ran). Two things hid it: (1) a pipeline's exit status is the **last** command's (`tail` → 0); (2) stdout is block-buffered in a pipe, so the JSON report printed in `finally` was flushed **after** the traceback, and `tail` kept the JSON and cut the traceback. Re-running Part 52 alone succeeded, so the error was transient (exact error lost to `tail`).
- **Fix:** each part runs in its own try/except, failures go to `parts_failed` + stderr, the report is flushed, exit code 1 if any part failed. Use `set -o pipefail` when piping. Parts 52 and 53 re-ingested → 4,065 docs, citation now `FAR 52.212-4(v); (a)`.
- **Lesson:** a batch job's report must count *failures*, not just work done; and never trust `$?` through a pipe.

## 2026-11-14 – Search alias PUT → 400 "The version indicated by the api-version query string parameter does not exist."
- **Where:** `infra/logs/07b-alias.log`, `PUT https://srch-cczq9h.search.windows.net/aliases/far-chunks?api-version=2024-07-01`.
- **Root cause:** aliases aren't in the 2024-07-01 data-plane API; the error message says the *version* doesn't exist, though it exists for other paths.
- **Fix:** `api-version=2026-10-01` (the version the Search SDK sends, seen in the 03 trace) → 201.

## 2026-11-14 – Unit tests exporting telemetry to Azure
- **Symptom:** `pytest` went from 1.1 s to 2.2 s after adding OpenTelemetry.
- **Root cause:** `telemetry.configure()` runs at import of `app.main` and falls back to reading `.env` from the cwd; test modules import the app before the `client` fixture `chdir("/")`s.
- **Fix:** `tests/conftest.py` sets `OTEL_SDK_DISABLED=true` before anything imports the app; `configure()` honors it. Verified: no tracer provider installed under tests.

## 2026-11-14 – Postgres create: `MissingSubscriptionRegistration`, hidden by a pipe
- **Symptom:** step 9 "finished" (exit 0) but `az postgres flexible-server show` → ResourceNotFound.
- **Where:** `infra/logs/09-pg.log`: PUT …/flexibleServers/pg-cczq9h → 409 `MissingSubscriptionRegistration` for `Microsoft.DBforPostgreSQL`.
- **Root cause:** the resource provider was never registered (same class as Storage in step 4). `set -e` did stop the script, but I ran it as `./setup.sh 9 | tail`, so the exit code was tail's. Same mistake as the Part 52 ingest.
- **Fix:** provider added to step 0's list and registered; long-running steps now run without a pipe (`> file; echo exit=$?`).

## 2026-11-14 – Postgres firewall rules: "not supported for a server without public access enabled"
- **Root cause:** `create --public-access None` disables the public endpoint entirely (not "no rules"); firewall rules need it enabled.
- **Fix:** step 9 runs `flexible-server update --public-access Enabled`, then adds `allow-azure` (0.0.0.0) and `dev-<date>` (my IP, looked up at run time, never committed). Also: `db create` takes `-n/--name`, not `-d`.

## 2026-11-14 – Live app down for a few minutes: revision pointed at an image that was never built
- **Symptom:** after `IMAGE_TAG=<HEAD> ./setup.sh 13`, the active revision showed image `copilot:8f8fd33`, health `None`, 100% traffic.
- **Where:** `infra/logs/13-ca.log`: "Failed to provision revision … BuildFailed: The container image 'acrcczq9h.azurecr.io/copilot:8f8fd33' was not found in the registry".
- **Root cause:** my command chain `commit && deploy.sh …; setup.sh 13` — a bad grep (`$ID_APP` read as a regex anchor) stopped the chain before commit+deploy, but step 13 (after `;`) still ran with the HEAD tag, which had never been pushed. The update **failed but still replaced the app's template**: the env vars landed and the single revision pointed at the missing image.
- **Fix:** commit → `deploy.sh` (build + push `6eeb721` + update image) → Healthy; live `/smoke` 6/6.
- **Lessons:** (1) step 13 must verify the image tag exists in ACR before updating (`az acr repository show-tags`); (2) in single-revision mode a failed update is not a no-op; (3) chain deploy steps with `&&` only.
