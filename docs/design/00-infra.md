# 00 – Infra (Step 0: Azure foundation)

> Write this BEFORE any code. Predict, then check against real traces.
> For each resource: fill **Predicted** before we run the step, then we fill **Observed**
> from `infra/logs/NN-*.log` and you rewrite it in your own words.

## 1. Requirements
**Functional**
-
**Non-functional** (latency target, cost/request, accuracy bar, security)
-
**Out of scope**
- Postgres, ACR, Container Apps (deferred for cost; created when /smoke and first deploy need them)

## 2. Core entities
-

## 3. API
Not an app API: the "API" here is Azure Resource Manager (control plane) and each service's
data-plane endpoint.
```
METHOD https://management.azure.com/<scope>/providers/<Namespace>/<type>/<name>?api-version=...
Auth:  bearer token, audience = ?
```

## 4. Data types, access patterns & scale
- Control plane vs data plane: what's the difference, and who calls each?
-

## 5. Data flow (numbered hops)
What happens between typing `az <thing> create` and the resource existing?
1.
2.

## 6. High-level design
(diagram / boxes and arrows: RG → resources → identity → role assignments)

## Resource ledger

### Step 0 – Provider registration + budget alert
_(Predictions skipped for this step by choice.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | **Provider registration:** turns on a resource namespace (e.g. `Microsoft.Storage`) for *this subscription*. Before it, ARM rejects calls to that namespace; Storage answered with a misleading `SubscriptionNotFound`. **Budget:** a `Microsoft.Consumption/budgets` object at subscription scope that alerts and never stops spending. |
| ARM call | – | **Register:** `POST https://management.azure.com/subscriptions/{sub}/providers/Microsoft.Storage/register?api-version=2024-11-01` → **200** (×7, one per namespace). `--wait` then polled `GET .../providers/{ns}` 45 times until `registrationState=Registered`, so registration is **async**. **Budget:** `PUT .../subscriptions/{sub}/providers/Microsoft.Consumption/budgets/budget-contract-copilot?api-version=2023-05-01` → **401 `RequestDisallowedByAzure`**, because ARM write blocked: token had no MFA claim (`amr:["pwd"]`). After re-login with MFA (`amr:["pwd","mfa"]`): same PUT → **201 Created**. Re-running it would return 200 (update), so PUT is idempotent. |
| Control-plane access | – | Token audience `https://management.core.windows.net/` (ARM), issued by Entra for the signed-in user via MSAL. Register needs `*/register/action` on the subscription (Owner and Contributor both have it). Budget write needs Cost Management Contributor, Contributor or Owner. **Azure mandatory MFA:** user write ops on ARM need a token with `acrs=p1`. ARM returned `WWW-Authenticate: insufficient_claims` with claims `{"access_token":{"acrs":{"essential":true,"values":["p1"]}}}`. |
| Data-plane access | – | None. Both are control-plane only. |
| Cost | – | $0 for both. |

### Step 1 – Resource group `rg-contract-copilot`
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | A logical container and an RBAC/policy scope. Its `location` (eastus2) only stores the group's metadata; each resource picks its own region. Deleting it deletes everything inside it. |
| ARM call | – | `PUT https://management.azure.com/subscriptions/{sub}/resourcegroups/rg-contract-copilot?api-version=2024-11-01`, body `{"location":"eastus2","tags":{...}}` → **201 Created**. Re-run → **200 OK**, because PUT is idempotent (create-or-update), so the script is safe to re-run. Synchronous, with no polling, unlike provider registration. Response headers: `x-ms-request-id` / `x-ms-correlation-request-id` (quote these to Azure support) and `x-ms-ratelimit-remaining-subscription-writes: 199` (ARM write throttle per subscription). |
| Control-plane access | – | ARM token (aud `https://management.core.windows.net/`). Nobody was assigned on the RG itself; all access is **inherited** down the scope chain: root `/` → management group (USC tenant) → subscription → RG. Me: Owner (subscription). USC IT: User Access Administrator at root and management group (could grant themselves anything), Cost Management Contributor and Billing Reader, plus a third-party access tool (Britive) with Reader and Foundry User at the management group. **So "who can access my RG" includes university admins I never added.** |
| Data-plane access | – | None. An RG has no data plane. |
| Cost | – | $0 |

### Step 2 – Log Analytics `log-cczq9h` + App Insights `appi-cczq9h` (canadacentral)
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | **Log Analytics workspace:** the log store, queried with KQL. **App Insights:** the APM layer (requests, dependencies, traces, the spans from OpenTelemetry). It is *workspace-based*: it has no storage of its own and writes into the workspace (`IngestionMode: LogAnalytics`). |
| ARM call | – | **First attempt (eastus2):** `PUT …/Microsoft.OperationalInsights/workspaces/log-cczq9h` → **403 `RequestDisallowedByAzure`**, blocked by the subscription policy "Allowed resource deployment regions". **Workspace:** `PUT …/Microsoft.OperationalInsights/workspaces/log-cczq9h?api-version=2025-02-01`, body `{location, sku:PerGB2018, retentionInDays:30, workspaceCapping:{dailyQuotaGb:0.1}}` → **201**, then **async**: the response's `Location` header pointed at `…/locations/canadacentral/operationstatuses/{id}`, which the CLI polled (GET ×2) until done. **App Insights:** `PUT …/Microsoft.Insights/components/appi-cczq9h?api-version=2020-02-02`, body includes `"WorkspaceResourceId": "<workspace ARM id>"`, so the link between them is one resource's ARM ID in the other's body → **200**, synchronous. |
| Control-plane access | – | ARM token; inherited Owner (me) plus USC admins (see step 1). |
| Data-plane access | – | **Ingestion (app → App Insights):** connection string `InstrumentationKey=…;IngestionEndpoint=https://canadacentral-1.in.applicationinsights.azure.com/`. The ikey is an *identifier*, not a secret: anyone with it can send telemetry, but nobody can read data with it. Local auth is currently enabled (`disableLocalAuth: null`). To make ingestion Entra-only, set `DisableLocalAuth=true` and give the app identity *Monitoring Metrics Publisher* (later). **Query:** Entra token for `https://api.loganalytics.io`, role *Log Analytics Reader* (or Reader+) on the workspace. |
| Cost | – | Pay per GB ingested, first 5 GB/month free. Daily cap 0.1 GB means at most ~3 GB/month, so ~$0. Retention 30 days is included. |

### Step 3 – Key Vault `kv-cczq9h` (canadacentral, RBAC mode)
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | A managed store for secrets, keys and certs. **RBAC mode**: data access is granted by Azure role assignments, not the legacy per-vault "access policies" (`accessPolicies: []`). Soft delete is always on: a deleted vault keeps its name reserved for 7 days. Purge protection is off (dev). |
| ARM call | – | The CLI first sent `GET …/Microsoft.KeyVault/vaults/kv-cczq9h` → **404**, a client-side existence check (an `az` behaviour, not ARM). Then `PUT …/Microsoft.KeyVault/vaults/kv-cczq9h?api-version=2026-02-01`, body `{location, properties:{tenantId, sku:standard, accessPolicies:[], enableRbacAuthorization:true, softDeleteRetentionInDays:7, networkAcls:{defaultAction:Allow, bypass:AzureServices}}}` → **200**, then GET ×2 polling until provisioned. Note that `tenantId` is in the body: the vault trusts tokens from *one* Entra tenant only. |
| Control-plane access | – | ARM token. Owner (me, inherited) can create, delete or configure the vault and **grant roles on it**, but that does not include reading secrets. |
| Data-plane access | – | Endpoint `https://kv-cczq9h.vault.azure.net/`, token scope `https://vault.azure.net/.default`. **Test as Owner:** `GET /secrets?api-version=7.4` → (1) **401** with no token, plus `WWW-Authenticate: Bearer authorization="https://login.microsoftonline.com/{tenant}", resource="https://vault.azure.net"` (the challenge tells the client *which tenant* and *which audience* to get a token for) → (2) retry with a vault token → **403 Forbidden** "Caller is not authorized". **Owner is a control-plane role with no `dataActions`**, so step 8 must grant *Key Vault Secrets Officer* (me) and *Key Vault Secrets User* (app). |
| Cost | – | Standard: no monthly fee, ~$0.03 per 10k operations. Effectively $0. |

### Step 4 – Storage `stcczq9h` (canadacentral) + containers `far-raw`, `contracts`
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | StorageV2 account, Standard_LRS (3 copies in one datacenter), Hot tier. It holds FAR source files and uploaded contract PDFs. Entra-only: `allowSharedKeyAccess:false`, `allowBlobPublicAccess:false`, TLS 1.2+, HTTPS only. |
| ARM call | – | (1) `POST …/subscriptions/{sub}/providers/Microsoft.Storage/checkNameAvailability` → 200 (names are global DNS: `stcczq9h.blob.core.windows.net`). (2) `PUT …/Microsoft.Storage/storageAccounts/stcczq9h?api-version=2025-08-01`, body `{sku, kind, location, properties:{allowSharedKeyAccess:false, allowBlobPublicAccess:false, minimumTlsVersion:TLS1_2, …}}` → **202 Accepted**, with a `Location` header → `…/locations/canadacentral/asyncoperations/{id}?monitor=true` → poll: **202** (still running), then **200** (done). This is the classic **202 + Location** long-running-operation pattern (Log Analytics used 201 + Location). (3) Containers via ARM: `PUT …/storageAccounts/stcczq9h/blobServices/default/containers/far-raw` → **201** (×2). A container is also an ARM child resource, so it was created *without* any blob data role. |
| Control-plane access | – | ARM token. Owner can still **list the account keys** (`POST …/listKeys`), but with shared key disabled those keys are useless. |
| Data-plane access | – | Endpoint `https://stcczq9h.blob.core.windows.net`, token scope `https://storage.azure.com/.default`. **Entra token as Owner:** `GET /far-raw?restype=container&comp=list` → **403 `AuthorizationPermissionMismatch`** (valid token, no data role). **Account key:** → **`KeyBasedAuthenticationNotPermitted`**. So the *only* way in is Entra plus a data role: step 8 grants *Storage Blob Data Contributor* (me) and *Storage Blob Data Reader* (app). |
| Cost | – | ~$0.02/GB-month (Hot LRS) plus fractions of a cent per 10k operations. ~$0 for MBs of FAR XML. |

### Step 5 – User-assigned managed identity `id-app-cczq9h`
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | The app's own identity. **One ARM call creates two objects:** an Azure resource (`Microsoft.ManagedIdentity/userAssignedIdentities`) *and* a service principal in Entra ID (`servicePrincipalType: ManagedIdentity`). There are no secrets: Azure rotates the credential internally, and code gets tokens from the host's identity endpoint (IMDS / Container Apps' identity endpoint) through `DefaultAzureCredential` → `ManagedIdentityCredential`. User-assigned, not system-assigned, because it exists before the app, can be granted roles now, and survives app re-creation. |
| ARM call | – | `PUT …/Microsoft.ManagedIdentity/userAssignedIdentities/id-app-cczq9h?api-version=2025-05-31-preview`, body just `{"location":"canadacentral"}` → **201**, synchronous. The response gives three IDs: `principalId` c122c2ff-… (the **service principal's object ID**, what role assignments target), `clientId` 8e1e76a2-… (= the SP's **appId**, what code passes as `AZURE_CLIENT_ID` to choose *which* identity when a host has several), `tenantId`. |
| Control-plane access | – | ARM: Owner/Contributor can create or delete it. *Managed Identity Operator* is needed to **attach** it to a compute resource (e.g. a Container App), which stops anyone who can deploy an app from borrowing any identity. Reading it in Entra used a **different token**: `GET https://graph.microsoft.com/v1.0/servicePrincipals/{principalId}` with scope `https://graph.microsoft.com/.default`. The first Graph read right after the create → **404 `Request_ResourceNotFound`**: Entra replication lag (seconds). A retry a few seconds later → 200. |
| Data-plane access | – | None of its own. It's a *principal*, not a resource with data. What it can reach is exactly the role assignments in step 8. |
| Cost | – | Free. |

### Step 6 – AI Services `ais-cczq9h` (**francecentral**) + deployments `chat`, `embed`
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | A Foundry / AI Services account (`kind: AIServices`, S0): one endpoint that serves Azure OpenAI and other models. A **deployment** is a named, quota-bearing instance of a model inside it: `chat` → gpt-5-mini 2025-08-07, `embed` → text-embedding-3-small v1, both GlobalStandard, 50K TPM. The app references deployment names only. **Pre-check:** `az cognitiveservices usage list -l <region>` showed the Students subscription has **0 quota** for gpt-4.1-mini/gpt-4o-mini in every allowed region. gpt-5-mini has 500K TPM in francecentral and norwayeast, so the account lives in francecentral (the rest of the stack stays in canadacentral). |
| ARM call | – | (1) `PUT …/Microsoft.CognitiveServices/accounts/ais-cczq9h?api-version=2026-09-15-preview`, body `{kind:AIServices, sku:S0, location:francecentral, properties:{customSubDomainName:ais-cczq9h}}` → **201**, then async poll `…/locations/francecentral/operationResults/{id}` (GET ×2). (2) Disable keys: `az resource update` = GET the resource, then **PUT the whole resource back** with `disableLocalAuth:true` → 200 + async poll. A generic update is read-modify-write, not PATCH. (3) `PUT …/accounts/ais-cczq9h/deployments/chat` → **201**; same for `…/deployments/embed` → **201**. Deployments are ARM child resources. |
| Control-plane access | – | ARM token. Owner/Contributor (or *Cognitive Services Contributor*) can create the account and deployments and change TPM capacity. Listing keys is moot: local auth is off. |
| Data-plane access | – | Endpoint `https://ais-cczq9h.cognitiveservices.azure.com/` (the custom subdomain is **required** for Entra tokens), scope `https://cognitiveservices.azure.com/.default`. **My token, no role:** `POST /openai/deployments/embed/embeddings?api-version=2024-10-21` → **401 `PermissionDenied`**: "lacks the required data action `Microsoft.CognitiveServices/accounts/OpenAI/deployments/embeddings/action`". The error names the exact `dataAction` a role must grant. **`api-key` header** → **401** (keys disabled). Step 8: *Cognitive Services OpenAI User* for me and the app. |
| Cost | – | No monthly fee. Pay per token: gpt-5-mini ≈ $0.25 / 1M input, $2 / 1M output tokens; text-embedding-3-small ≈ $0.02 / 1M tokens (list prices, verify in the portal). Embedding the entire FAR ≈ a few cents. Reasoning models also bill hidden "reasoning tokens" as output. |

### Step 7 – AI Search `srch-cczq9h` (canadacentral, Free)
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | A search engine for keyword (BM25), vector and hybrid (RRF) retrieval over indexes we define. Free tier: 1 per subscription, 50 MB, 3 indexes, shared infrastructure, no SLA. ARM reports `semanticSearch: "free"`; whether the semantic ranker actually runs on the Free SKU is **unverified**, to be tested in the RAG feature. |
| ARM call | – | `PUT …/Microsoft.Search/searchServices/srch-cczq9h?api-version=2026-03-01-preview`, body `{location, sku:{name:free}, properties:{replicaCount:1, partitionCount:1, authOptions:{aadOrApiKey:{aadAuthFailureMode:http401WithBearerChallenge}}}}` → **201**. No polling needed on Free (paid tiers provision for minutes). `authOptions` is the switch that **turns Entra on** for the data plane; Search defaults to keys only. |
| Control-plane access | – | ARM token. Owner/Contributor/*Search Service Contributor* manage the service. Admin keys come from `POST …/listAdminKeys` (ARM), so anyone with that action can mint full data access. That's why the goal is `disableLocalAuth` once the app is on tokens. |
| Data-plane access | – | Endpoint `https://srch-cczq9h.search.windows.net`, token scope `https://search.azure.com/.default`. **Surprise:** my Entra token with *no Search data role* → `GET /indexes?api-version=2024-07-01` → **200** `{"value":[]}`. Unlike Key Vault, Storage and AI Services, Search maps **index *definitions*** (create/list/delete index schema) to ordinary `actions` (`Microsoft.Search/searchServices/indexes/*`), which Owner has. **Documents** (query, upload) are `dataActions`, which need *Search Index Data Reader/Contributor*. To verify once an index exists: a doc query with no data role → 403. **Admin `api-key`** → 200 (keys still enabled under `aadOrApiKey`). |
| Cost | – | $0 (Free). Basic ≈ $74/mo is the upgrade path (semantic ranker, SLA, 2 GB+). |

### Step 8 – Role assignments
_(Predictions skipped.)_
| | Predicted | Observed |
|---|---|---|
| What it is | – | A role assignment = **(principal, role definition, scope)**. It is itself an ARM resource (`Microsoft.Authorization/roleAssignments/{guid}`) that lives *under* the scope it applies to. Scoped per resource, not per RG (least privilege). **App identity:** Key Vault Secrets User, Storage Blob Data Reader, Cognitive Services OpenAI User, Search Index Data Reader (AcrPull later). **Me:** Key Vault Secrets Officer, Storage Blob Data Contributor, Cognitive Services OpenAI User, Search Index Data Contributor, Search Service Contributor. |
| ARM call | – | My object ID via **Graph**: `az ad signed-in-user show` = `GET https://graph.microsoft.com/v1.0/me` (Graph token). Then 9× `PUT https://management.azure.com/{resource-id}/providers/Microsoft.Authorization/roleAssignments/{new-guid}?api-version=2022-04-01`, body `{"properties":{"principalType":"ServicePrincipal","principalId":"<oid>","roleDefinitionId":"/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions/4633458b-…"}}` → **201** each. The role is referenced by a **built-in GUID** (4633458b-… = Key Vault Secrets User), the same in every tenant. The client picks the assignment GUID, which makes the PUT idempotent. `--assignee-principal-type` skipped a Graph lookup, avoiding the step-5 replication race. |
| Control-plane access | – | Creating assignments needs `Microsoft.Authorization/roleAssignments/write`: **Owner**, **User Access Administrator** or **Role Based Access Control Administrator**, *not* Contributor. So a Contributor can build everything except grant access. |
| Data-plane access | – | Re-ran the earlier failures as me: Key Vault `GET /secrets` 403 → **200**, Storage list blobs 403 → **200** (both within ~1 min). AI Services: **chat → 200 straight away, but embed stayed 401 `PermissionDenied` for ~8 min** (11:14 → 11:22) with the *same* role and the *same* token. RBAC is **eventually consistent per data-plane node/cache**, not per role. Search documents: unverified until an index exists. |
| Cost | – | Free. Limit: 4,000 role assignments per subscription. |

### Not yet created
- PostgreSQL Flexible `pg-$SFX`, ACR `acr$SFX`, Container Apps `cae-$SFX` / `ca-copilot-$SFX`

## 7. Expected deep-dive questions
1.
2.
3.

---
## After building
### Trace vs prediction (what I got wrong)
-
### Break-it results
-
### 30-second explanation
-
