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
  Microsoft.App Microsoft.ContainerRegistry   # added for feature 02 (deploy)
  Microsoft.DBforPostgreSQL                  # added for feature 06 (create failed with MissingSubscriptionRegistration)
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

# Step 2b (design 04): Entra-only telemetry ingestion. With local auth on, anyone holding the
# connection string (it embeds the instrumentation key) can write telemetry. With it off, the
# exporter must send an Entra token (scope https://monitor.azure.com/.default) from a principal
# with "Monitoring Metrics Publisher" on this component (step 8). ARM PATCH on the component.
step_2b_appi_entra() {
  run 02b-appi-entra az resource update -g "$RG" -n "$APPI" --resource-type Microsoft.Insights/components \
    --set properties.DisableLocalAuth=true -o none
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
EMBED_MODEL="text-embedding-3-small"; EMBED_VERSION="1";         EMBED_TPM_K=300  # 50→300 for ingestion (design 03); per-token billing, capacity is only a rate limit
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

# Step 6b: resize `embed` only (design 03). Same ARM PUT on .../deployments/embed as step 6;
# PUT is idempotent, so re-sending it with a new sku.capacity updates the rate limit in place.
step_6b_embed_capacity() {
  run 06b-embed-capacity az cognitiveservices account deployment create -g "$RG" -n "$AIS" \
    --deployment-name embed --model-format OpenAI --model-name "$EMBED_MODEL" \
    --model-version "$EMBED_VERSION" --sku-name GlobalStandard --sku-capacity "$EMBED_TPM_K" -o none
}

# Step 7: Azure AI Search, Free tier ($0; 1 per subscription, 50 MB, 3 indexes, no semantic
# ranker, no SLA). aadOrApiKey turns ON Entra (RBAC) data-plane auth; by default Search is
# key-only. http401WithBearerChallenge: a bad token gets a 401 + WWW-Authenticate challenge.
SRCH="srch-$SFX"
step_7_search() {
  run 07-srch az search service create -g "$RG" -n "$SRCH" -l "$LOCATION" --sku free \
    --auth-options aadOrApiKey --aad-auth-failure-mode http401WithBearerChallenge -o none
}

# Step 7b (design 04): index alias. The app queries `far-chunks`; a schema change builds
# far-chunks-v2 and repoints this alias, with no app redeploy. NOT an ARM call: aliases are a
# Search data-plane object (PUT {endpoint}/aliases/{name}), so the token is for
# https://search.azure.com and the role is Search Service Contributor (me).
SEARCH_ALIAS="far-chunks"; SEARCH_INDEX_VERSION="${SEARCH_INDEX_VERSION:-far-chunks-v2}"   # design 05: v2 won on held-out
step_7b_alias() {
  run 07b-alias az rest --method put --resource https://search.azure.com \
    --url "https://$SRCH.search.windows.net/aliases/$SEARCH_ALIAS?api-version=2026-10-01" \
    --headers Content-Type=application/json \
    --body "{\"name\": \"$SEARCH_ALIAS\", \"indexes\": [\"$SEARCH_INDEX_VERSION\"]}" -o none
}

# Step 8: role assignments (least privilege, scoped to each resource, not the RG). Free.
# --assignee-object-id + --assignee-principal-type skips the Graph lookup, which avoids the
# "principal not found" race right after an identity is created (Entra replication lag, step 5).
assign() {  # assign <log-name> <principal-object-id> <User|ServicePrincipal> <role> <scope>
  local log="$1" oid="$2" ptype="$3" role="$4" scope="$5"
  if [[ -n "$(az role assignment list --assignee "$oid" --role "$role" --scope "$scope" --query '[0].id' -o tsv)" ]]; then
    echo "exists: $role → ${scope##*/}" >&2; return
  fi
  run "$log" az role assignment create --assignee-object-id "$oid" --assignee-principal-type "$ptype" \
    --role "$role" --scope "$scope" -o none
}

step_8_roles() {
  local me app kv st ais srch
  me="$(az ad signed-in-user show --query id -o tsv)"     # Graph: GET /v1.0/me
  app="$(az identity show -g "$RG" -n "$ID_APP" --query principalId -o tsv)"
  kv="$(az keyvault show -g "$RG" -n "$KV" --query id -o tsv)"
  st="$(az storage account show -g "$RG" -n "$ST" --query id -o tsv)"
  ais="$(az cognitiveservices account show -g "$RG" -n "$AIS" --query id -o tsv)"
  srch="$(az search service show -g "$RG" -n "$SRCH" --query id -o tsv)"
  local appi; appi="$(az monitor app-insights component show -g "$RG" -a "$APPI" --query id -o tsv)"

  # App identity: read-only on data, except what it must call.
  assign 08-roles-app "$app" ServicePrincipal "Key Vault Secrets User"          "$kv"
  assign 08-roles-app "$app" ServicePrincipal "Storage Blob Data Reader"        "$st"
  assign 08-roles-app "$app" ServicePrincipal "Cognitive Services OpenAI User"  "$ais"
  assign 08-roles-app "$app" ServicePrincipal "Search Index Data Reader"        "$srch"
  # Index DEFINITIONS (list/get index schema) are control-plane actions in Search, not data
  # actions (step 7 finding). /smoke's list_index_names → 403 for the MI without this.
  # Reader is read-only on the service and can't call listAdminKeys (a POST action).
  assign 08-roles-app "$app" ServicePrincipal "Reader"                          "$srch"
  # Write telemetry with an Entra token (step 2b turns key-based ingestion off).
  assign 08-roles-app "$app" ServicePrincipal "Monitoring Metrics Publisher"    "$appi"
  # AcrPull: added when the container registry is created.

  # Me (local dev + ingestion): write access to data, plus Search index management.
  assign 08-roles-me "$me" User "Key Vault Secrets Officer"       "$kv"
  assign 08-roles-me "$me" User "Storage Blob Data Contributor"   "$st"
  assign 08-roles-me "$me" User "Cognitive Services OpenAI User"  "$ais"
  assign 08-roles-me "$me" User "Search Index Data Contributor"   "$srch"
  assign 08-roles-me "$me" User "Search Service Contributor"      "$srch"
  assign 08-roles-me "$me" User "Monitoring Metrics Publisher"    "$appi"
}

# Step 9 (design 06): PostgreSQL Flexible Server, Burstable B1ms, PG16. COST: $0.0185/hour ≈ $13.50/month
# while RUNNING (+ storage, billed even when stopped). Stop when idle: `./infra/setup.sh 9z`; Azure auto-starts
# a stopped server after 7 days. ARM: PUT Microsoft.DBforPostgreSQL/flexibleServers/pg-<sfx> (async, minutes).
# Auth: Microsoft Entra ONLY (password auth disabled: there is no admin password to store or leak).
# Network: public endpoint. Our express ACA env has no outbound IPs/VNet, so the app can't be pinned by IP;
# rule "allow-azure" (0.0.0.0) admits Azure-originated traffic, rule "dev-<date>" admits my current IP.
# Reaching 5432 isn't enough: a caller needs an Entra token for a principal we created (accepted risk, design 06).
PG="pg-$SFX"; PG_DB="copilot"
step_9_postgres() {
  local my_ip; my_ip="$(curl -s https://api.ipify.org)"   # looked up at run time, never committed
  if ! az postgres flexible-server show -g "$RG" -n "$PG" -o none 2>/dev/null; then
    run 09-pg az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOCATION" \
      --tier Burstable --sku-name Standard_B1ms --version 16 --storage-size 32 \
      --microsoft-entra-auth Enabled --password-auth Disabled \
      --public-access None --backup-retention 7 --yes -o none
  fi
  local me upn
  me="$(az ad signed-in-user show --query id -o tsv)"; upn="$(az ad signed-in-user show --query userPrincipalName -o tsv)"
  # Entra admin = me. Admins can create other Entra principals (the app MI) inside Postgres (step 9c).
  run 09-pg-admin az postgres flexible-server microsoft-entra-admin create -g "$RG" -s "$PG" \
    --display-name "$upn" --object-id "$me" --type User -o none
  # Create used --public-access None, which turns the public endpoint OFF entirely ("Firewall rule operations
  # are not supported for a server without public access enabled"). Turn it on; the rules below gate it.
  run 09-pg-public az postgres flexible-server update -g "$RG" -n "$PG" --public-access Enabled -o none
  run 09-pg-fw-azure az postgres flexible-server firewall-rule create -g "$RG" -s "$PG" \
    -n allow-azure --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none
  run 09-pg-fw-dev az postgres flexible-server firewall-rule create -g "$RG" -s "$PG" \
    -n "dev-$(date +%Y%m%d)" --start-ip-address "$my_ip" --end-ip-address "$my_ip" -o none
  run 09-pg-db az postgres flexible-server db create -g "$RG" -s "$PG" -n "$PG_DB" -o none
  # Raw USAspending downloads (lineage + --from-blob replays), like far-raw for the FAR.
  run 09-blob az storage container create --account-name "$ST" -n usaspending-raw --auth-mode login -o none
}

# Step 9c (design 06): the app MI's Postgres login, read-only. Runs SQL as the Entra admin (me):
# pgaadauth_create_principal('id-app-<sfx>') → GRANT copilot_reader → role-level read-only + 5 s timeout.
# Needs the awards schema first (the loader creates copilot_reader).
step_9c_pg_app() {
  run_py 09c-pg-app uv run python -m awards.admin grant-app "$ID_APP"
}

# Step 9z: stop Postgres to stop compute billing (storage still bills). Start again with 9y.
step_9z_pg_stop()  { run 09z-pg-stop  az postgres flexible-server stop  -g "$RG" -n "$PG" -o none; }
step_9y_pg_start() { run 09y-pg-start az postgres flexible-server start -g "$RG" -n "$PG" -o none; }

# Step 10: Azure Container Registry, Basic. COST: ~$0.167/day ≈ $5/month (the only fixed cost).
# Admin user disabled: it's a static username/password. Pushes use my Entra token (az acr login),
# pulls use the app's managed identity. Push/pull roles are data-plane roles, like Key Vault.
ACR="acr$SFX"
step_10_acr() {
  run 10-acr az acr create -g "$RG" -n "$ACR" -l "$LOCATION" --sku Basic --admin-enabled false -o none
  local me app acr_id
  me="$(az ad signed-in-user show --query id -o tsv)"
  app="$(az identity show -g "$RG" -n "$ID_APP" --query principalId -o tsv)"
  acr_id="$(az acr show -g "$RG" -n "$ACR" --query id -o tsv)"
  assign 10-acr-roles "$me"  User             "AcrPush" "$acr_id"
  assign 10-acr-roles "$app" ServicePrincipal "AcrPull" "$acr_id"
}

# Step 11: Container Apps environment. Consumption-only: no charge for the environment itself.
# Wanted: --logs-destination azure-monitor (the default "log-analytics" needs the workspace SHARED
# KEY in the ARM body). ARM rejected it: 400 ExpressAzureMonitorLogDestNotSupported ("not
# supported ... on express environments"). So: destination none + a diagnostic setting into
# log-$SFX. Whether logs actually flow with destination=none is verified after deploy.
CAE="cae-$SFX"
step_11_cae() {
  run 11-cae az containerapp env create -g "$RG" -n "$CAE" -l "$LOCATION" \
    --logs-destination none -o none
  local cae_id law_id
  cae_id="$(az containerapp env show -g "$RG" -n "$CAE" --query id -o tsv)"
  law_id="$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query id -o tsv)"
  run 11-cae-diag az monitor diagnostic-settings create -n to-log-analytics --resource "$cae_id" \
    --workspace "$law_id" --logs '[{"categoryGroup":"allLogs","enabled":true}]' -o none
}

# Step 12: Entra app registration for sign-in (Microsoft Graph, not ARM). Free.
# - single tenant, ID tokens on, redirect = Easy Auth callback on the app's FQDN
# - NO client secret: Easy Auth then uses the ID-token flow (sign-in only, no downstream tokens)
# - its service principal ("enterprise app") has appRoleAssignmentRequired=true and only I am
#   assigned, so other USC users get an error from Entra instead of a token
CA="ca-copilot-$SFX"
APPREG="contract-copilot-web"
ca_fqdn() { echo "$CA.$(az containerapp env show -g "$RG" -n "$CAE" --query properties.defaultDomain -o tsv)"; }
step_12_appreg() {
  local app_id sp_id me fqdn
  fqdn="$(ca_fqdn)"
  app_id="$(az ad app list --display-name "$APPREG" --query '[0].appId' -o tsv)"
  if [[ -z "$app_id" ]]; then
    app_id="$(run 12-appreg az ad app create --display-name "$APPREG" --sign-in-audience AzureADMyOrg \
      --web-redirect-uris "https://$fqdn/.auth/login/aad/callback" --enable-id-token-issuance true \
      --query appId -o tsv)"
  else
    echo "exists: app registration $APPREG" >&2
  fi
  sp_id="$(az ad sp list --filter "appId eq '$app_id'" --query '[0].id' -o tsv)"
  [[ -n "$sp_id" ]] || sp_id="$(run 12-appreg az ad sp create --id "$app_id" --query id -o tsv)"
  run 12-appreg az ad sp update --id "$sp_id" --set appRoleAssignmentRequired=true
  me="$(az ad signed-in-user show --query id -o tsv)"
  if [[ -z "$(az rest --method get --url "https://graph.microsoft.com/v1.0/servicePrincipals/$sp_id/appRoleAssignedTo" \
        --query "value[?principalId=='$me'].id | [0]" -o tsv)" ]]; then
    # appRoleId all-zeros = "default access" (the app defines no roles of its own)
    run 12-appreg az rest --method post \
      --url "https://graph.microsoft.com/v1.0/servicePrincipals/$sp_id/appRoleAssignedTo" \
      --body "{\"principalId\":\"$me\",\"resourceId\":\"$sp_id\",\"appRoleId\":\"00000000-0000-0000-0000-000000000000\"}" -o none
  fi
  expose_api "$app_id"
  echo "APPREG_CLIENT_ID=$app_id" >&2
}

# Design 02 revision: the app validates Entra access tokens itself (Easy Auth is unavailable on
# express environments). So the registration exposes an API scope, issues v2 tokens, and
# pre-authorizes the Azure CLI so `az account get-access-token --scope api://<appId>/access_as_user`
# works without a consent prompt.
AZURE_CLI_APP_ID="04b07795-8ddb-461a-bbee-02f9e1bf7b46"   # Microsoft's well-known Azure CLI client
expose_api() {
  local app_id="$1" obj scope_id url
  obj="$(az ad app show --id "$app_id" --query id -o tsv)"
  url="https://graph.microsoft.com/v1.0/applications/$obj"
  scope_id="$(az ad app show --id "$app_id" --query "api.oauth2PermissionScopes[?value=='access_as_user'].id | [0]" -o tsv)"
  if [[ -z "$scope_id" ]]; then
    scope_id="$(uuidgen | tr 'A-Z' 'a-z')"
    run 12-expose-api az rest --method patch --url "$url" --body "{
      \"identifierUris\": [\"api://$app_id\"],
      \"api\": {\"requestedAccessTokenVersion\": 2, \"oauth2PermissionScopes\": [{
        \"id\": \"$scope_id\", \"value\": \"access_as_user\", \"type\": \"User\", \"isEnabled\": true,
        \"adminConsentDisplayName\": \"Call Contract Copilot\", \"adminConsentDescription\": \"Call the Contract Copilot API as the signed-in user\",
        \"userConsentDisplayName\": \"Call Contract Copilot\", \"userConsentDescription\": \"Call the Contract Copilot API as you\"}]}}" -o none
  fi
  # Second PATCH: pre-authorization must reference a scope that already exists.
  run 12-expose-api az rest --method patch --url "$url" --body "{\"api\": {\"preAuthorizedApplications\": [
    {\"appId\": \"$AZURE_CLI_APP_ID\", \"delegatedPermissionIds\": [\"$scope_id\"]}]}}" -o none
}

# Step 13: the Container App. Cost: consumption, min replicas 0 → inside the monthly free grant.
# Identity: id-app-$SFX is used for BOTH the image pull and the app's own Azure calls
# (AZURE_CLIENT_ID picks it inside DefaultAzureCredential).
# FAIL-CLOSED ORDER (design 02 revision): create/update with ingress off → set auth env → probes →
# verify AUTH_REQUIRED=true on the app → only then open external ingress.
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$(dirname "$0")/.." rev-parse --short HEAD)}"
step_13_app() {
  local id_res id_client app_id tenant
  id_res="$(az identity show -g "$RG" -n "$ID_APP" --query id -o tsv)"
  id_client="$(az identity show -g "$RG" -n "$ID_APP" --query clientId -o tsv)"
  app_id="$(az ad app list --display-name "$APPREG" --query '[0].appId' -o tsv)"
  tenant="$(az account show --query tenantId -o tsv)"
  local appi_conn   # not a secret: local auth is off (step 2b), the MI needs an Entra token to write
  appi_conn="$(az monitor app-insights component show -g "$RG" -a "$APPI" --query connectionString -o tsv)"
  local env_vars=(
    AZURE_CLIENT_ID="$id_client"
    AZURE_OPENAI_ENDPOINT="https://$AIS.cognitiveservices.azure.com/"
    AZURE_OPENAI_API_VERSION=2025-04-01-preview
    CHAT_DEPLOYMENT=chat EMBED_DEPLOYMENT=embed
    SEARCH_ENDPOINT="https://$SRCH.search.windows.net"
    KEY_VAULT_URL="https://$KV.vault.azure.net/"
    STORAGE_ACCOUNT_URL="https://$ST.blob.core.windows.net" STORAGE_CONTAINER=far-raw
    SMOKE_TIMEOUT_S=20
    AUTH_REQUIRED=true AUTH_TENANT_ID="$tenant" AUTH_AUDIENCE="$app_id"
    SEARCH_INDEX="$SEARCH_ALIAS"                                    # design 04: query the alias
    APPLICATIONINSIGHTS_CONNECTION_STRING="$appi_conn" OTEL_SERVICE_NAME=copilot-api
    PG_HOST="$PG.postgres.database.azure.com" PG_DATABASE="$PG_DB" PG_USER="$ID_APP"   # design 06: MI's Entra name
  )

  if ! az containerapp show -g "$RG" -n "$CA" -o none 2>/dev/null; then
    run 13-ca az containerapp create -g "$RG" -n "$CA" --environment "$CAE" \
      --image "$ACR.azurecr.io/copilot:$IMAGE_TAG" \
      --user-assigned "$id_res" --registry-server "$ACR.azurecr.io" --registry-identity "$id_res" \
      --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi \
      --env-vars "${env_vars[@]}" -o none
  else
    run 13-ca az containerapp update -g "$RG" -n "$CA" --image "$ACR.azurecr.io/copilot:$IMAGE_TAG" \
      --set-env-vars "${env_vars[@]}" -o none
  fi

  # Probes on /health (design 01: never on /smoke). az containerapp has no probe flags → PATCH via ARM.
  run 13-ca-probes python3 "$(dirname "$0")/patch_probes.py" "$RG" "$CA"

  local auth_on
  auth_on="$(az containerapp show -g "$RG" -n "$CA" \
    --query "properties.template.containers[0].env[?name=='AUTH_REQUIRED'].value | [0]" -o tsv)"
  [[ "$auth_on" == "true" ]] || { echo "REFUSING to open ingress: AUTH_REQUIRED=$auth_on" >&2; return 1; }
  run 13-ingress az containerapp ingress enable -g "$RG" -n "$CA" --type external --target-port 8000 \
    --transport auto -o none
  echo "URL: https://$(az containerapp show -g "$RG" -n "$CA" --query properties.configuration.ingress.fqdn -o tsv)" >&2
}

run_py() {  # like run(), but for our Python helpers (no --debug flag to append)
  local name="$1"; shift; echo ">> $*" >&2; "$@" 2>&1 | tee -a "$LOG_DIR/$name.log"; return "${PIPESTATUS[0]}"
}

# ---- dispatch ---------------------------------------------------------------
step="${1:?usage: $0 <step-number>}"
fn="$(declare -F | awk '{print $3}' | grep -E "^step_${step}_" | head -1)"
[[ -n "$fn" ]] || { echo "no step $step defined" >&2; exit 1; }
"$fn"
