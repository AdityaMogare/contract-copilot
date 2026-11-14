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
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call (method, URL, api-version, status) | | |
| Control-plane access (who can manage it) | | |
| Data-plane access (endpoint, token scope, role) | | |
| Cost | | |

### Step 1 – Resource group `rg-contract-copilot`
| | Predicted | Observed |
|---|---|---|
| What it is | | |
| ARM call | | |
| Control-plane access | | |
| Data-plane access | | |
| Cost | | |

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
