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
