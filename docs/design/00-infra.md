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

### Step 2 – Log Analytics `log-$SFX` + App Insights `appi-$SFX`
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

### Step 3 – Key Vault `kv-$SFX`
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

### Step 4 – Storage `st$SFX`
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

### Step 5 – Managed identity `id-app-$SFX`
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

### Step 6 – AI Services `ais-$SFX` + deployments `chat`, `embed`
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

### Step 7 – AI Search `srch-$SFX` (Free)
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

### Step 8 – Role assignments
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

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
