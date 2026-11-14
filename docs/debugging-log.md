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
