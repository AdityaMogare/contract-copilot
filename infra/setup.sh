#!/usr/bin/env bash
# Reproducible Azure setup for Contract Intelligence Copilot.
# Usage:  ./infra/setup.sh <step>          e.g. ./infra/setup.sh 1
#         DEBUG=1 ./infra/setup.sh <step>  adds --debug, logs stderr to infra/logs/
# Every resource this project uses must be created here (CLAUDE.md rule).
set -euo pipefail

# ---- config -----------------------------------------------------------------
# .env (gitignored) holds non-secret local settings like SFX. Never secrets: those go in Key Vault.
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a
# Azure for Students policy "Allowed resource deployment regions" permits only:
# belgiumcentral, canadacentral, denmarkeast, francecentral, norwayeast (eastus2 → 403).
# canadacentral = closest to US users; gpt-4.1-mini + text-embedding-3-small available there.
LOCATION="canadacentral"
RG_LOCATION="eastus2"   # RG created before we hit the policy; RG location is metadata only
RG="rg-contract-copilot"
SFX="${SFX:?set SFX, a short unique suffix, e.g. SFX=ccp7x}"   # globally-unique names need it
# Azure for Students: spending limit On = hard stop when credit runs out (docs/status.md).
# Pinned so a changed CLI default can never create resources in the PAYG subscription.
SUB="aa6c86fe-3f91-41f5-83e3-63ae93f3cdeb"
az account set --subscription "$SUB"

LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"
mkdir -p "$LOG_DIR"

# ---- helpers ----------------------------------------------------------------
# run <log-name> az ...   → runs the az command; with DEBUG=1 appends --debug and
# sends stderr (where az writes its debug output) to infra/logs/<log-name>.log
run() {
  local name="$1"; shift
  if [[ "${DEBUG:-0}" == "1" ]]; then
    echo ">> $* --debug   (log: infra/logs/$name.log)" >&2
    "$@" --debug 2>>"$LOG_DIR/$name.log"
  else
    echo ">> $*" >&2
    "$@"
  fi
}

# arm <log-name> → just the ARM request/response lines from a debug log
arm() {
  grep -E "Request URL|Request method|Response status" "$LOG_DIR/$1.log"
}

# ---- steps ------------------------------------------------------------------
# (added one at a time, after predicting the ARM call in docs/design/00-infra.md)

# Step 0: subscription-level prerequisites. Costs $0.
#  - Register the resource providers steps 1-8 need. ARM refuses calls to an unregistered
#    namespace (we saw it as a misleading "SubscriptionNotFound" from Microsoft.Storage).
#  - $30/month cost budget with alerts to the subscription's Owners (contactRoles, so no
#    email address ends up in git). A budget ALERTS; it never stops spending.
PROVIDERS=(
  Microsoft.Storage Microsoft.KeyVault Microsoft.CognitiveServices Microsoft.Search
  Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity
)
BUDGET_NAME="budget-contract-copilot"

step_0_budget() {
  for p in "${PROVIDERS[@]}"; do
    state="$(az provider show -n "$p" --query registrationState -o tsv)"
    if [[ "$state" == "Registered" ]]; then echo "$p already registered" >&2; continue; fi
    run 00-providers az provider register --namespace "$p" --wait
  done

  local start; start="$(date -u +%Y-%m-01)"
  local body
  body=$(cat <<JSON
{
  "properties": {
    "category": "Cost",
    "amount": 30,
    "timeGrain": "Monthly",
    "timePeriod": { "startDate": "${start}T00:00:00Z", "endDate": "2027-12-01T00:00:00Z" },
    "notifications": {
      "actual_80pct":    { "enabled": true, "operator": "GreaterThan", "threshold": 80,
                           "thresholdType": "Actual",     "contactRoles": ["Owner"] },
      "forecast_100pct": { "enabled": true, "operator": "GreaterThan", "threshold": 100,
                           "thresholdType": "Forecasted", "contactRoles": ["Owner"] }
    }
  }
}
JSON
)
  # PUT is idempotent: re-running updates the same budget instead of creating a second one.
  run 00-budget az rest --method put \
    --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/budgets/$BUDGET_NAME?api-version=2023-05-01" \
    --body "$body" -o none
}

# Step 1: resource group. Costs $0. A logical container + RBAC/policy scope; deleting it
# deletes everything inside. Its location only stores metadata; resources pick their own region.
step_1_rg() {
  run 01-rg az group create --name "$RG" --location "$RG_LOCATION" \
    --tags project=contract-copilot env=dev owner=aditya -o none
}

# Step 2: Log Analytics workspace + workspace-based Application Insights.
# Cost: pay per GB ingested (first 5 GB/month free per billing account). The 0.1 GB/day cap
# bounds it at ~3 GB/month, so it stays in the free tier even if something logs in a loop.
LAW="log-$SFX"
APPI="appi-$SFX"
step_2_monitoring() {
  run 02-log az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOCATION" \
    --sku PerGB2018 --retention-time 30 --quota 0.1 -o none
  local law_id; law_id="$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query id -o tsv)"
  # Workspace-based: App Insights stores its telemetry IN the workspace above (classic mode is retired).
  run 02-appi az monitor app-insights component create -g "$RG" --app "$APPI" -l "$LOCATION" \
    --kind web --application-type web --workspace "$law_id" -o none
}

# Step 3: Key Vault in RBAC mode (data-plane access via Azure role assignments, not vault
# access policies). Cost: ~$0.03 per 10k secret operations; no monthly fee for Standard.
# Soft delete is always on: a deleted vault holds its name for retention-days (7 = the minimum).
# Purge protection left OFF for dev so the vault can be purged and the name reused.
KV="kv-$SFX"
step_3_keyvault() {
  run 03-kv az keyvault create -g "$RG" -n "$KV" -l "$LOCATION" --sku standard \
    --enable-rbac-authorization true --retention-days 7 -o none
}

# Step 4: Storage account for FAR source files and uploaded contract PDFs.
# Cost: Standard_LRS hot ≈ $0.02/GB-month + per-operation; ~$0 while nearly empty.
# Entra-only: shared-key (account keys / SAS signed with them) disabled, no anonymous blob access.
ST="st$SFX"
CONTAINERS=(far-raw contracts)
step_4_storage() {
  run 04-st az storage account create -g "$RG" -n "$ST" -l "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 --access-tier Hot \
    --allow-blob-public-access false --allow-shared-key-access false \
    --min-tls-version TLS1_2 --https-only true -o none
  # container-rm = create containers through ARM (control plane), so it works before
  # anyone has a blob data role. "az storage container create" would hit the data plane.
  for c in "${CONTAINERS[@]}"; do
    run 04-containers az storage container-rm create -g "$RG" --storage-account "$ST" -n "$c" -o none
  done
}

# Step 5: user-assigned managed identity = the app's own Entra identity. Free.
# User-assigned (not system-assigned) so it exists before the Container App does, roles can be
# granted now (step 8), and it survives the app being deleted/recreated.
ID_APP="id-app-$SFX"
step_5_identity() {
  run 05-id az identity create -g "$RG" -n "$ID_APP" -l "$LOCATION" -o none
}

# Step 6: Azure AI Services (Foundry) account + model deployments `chat` and `embed`.
# Region: francecentral, NOT $LOCATION. Students quota is 0 for gpt-4.1-mini/gpt-4o-mini in
# every allowed region; gpt-5-mini has 500K TPM GlobalStandard quota in francecentral.
# Cost: no monthly fee; pay per token (GlobalStandard). Capacity is in units of 1K TPM: kept low.
# Entra-only: local (key) auth disabled after create. Custom subdomain is required for Entra tokens.
AIS="ais-$SFX"
AIS_LOCATION="francecentral"
CHAT_MODEL="gpt-5-mini";             CHAT_VERSION="2025-08-07";  CHAT_TPM_K=50
EMBED_MODEL="text-embedding-3-small"; EMBED_VERSION="1";         EMBED_TPM_K=50
step_6_ai() {
  run 06-ais az cognitiveservices account create -g "$RG" -n "$AIS" -l "$AIS_LOCATION" \
    --kind AIServices --sku S0 --custom-domain "$AIS" --yes -o none
  run 06-ais-localauth az resource update -g "$RG" -n "$AIS" \
    --resource-type Microsoft.CognitiveServices/accounts --set properties.disableLocalAuth=true -o none
  # Deployment NAMES (chat, embed) are what the app references (CLAUDE.md), never model names,
  # so swapping the model behind `chat` needs no code change.
  run 06-deploy-chat az cognitiveservices account deployment create -g "$RG" -n "$AIS" \
    --deployment-name chat --model-format OpenAI --model-name "$CHAT_MODEL" \
    --model-version "$CHAT_VERSION" --sku-name GlobalStandard --sku-capacity "$CHAT_TPM_K" -o none
  run 06-deploy-embed az cognitiveservices account deployment create -g "$RG" -n "$AIS" \
    --deployment-name embed --model-format OpenAI --model-name "$EMBED_MODEL" \
    --model-version "$EMBED_VERSION" --sku-name GlobalStandard --sku-capacity "$EMBED_TPM_K" -o none
}

# ---- dispatch ---------------------------------------------------------------
step="${1:?usage: $0 <step-number>}"
fn="$(declare -F | awk '{print $3}' | grep -E "^step_${step}_" | head -1)"
[[ -n "$fn" ]] || { echo "no step $step defined" >&2; exit 1; }
"$fn"
