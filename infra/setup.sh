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
LOCATION="eastus2"
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

# ---- dispatch ---------------------------------------------------------------
step="${1:?usage: $0 <step-number>}"
fn="$(declare -F | awk '{print $3}' | grep -E "^step_${step}_" | head -1)"
[[ -n "$fn" ]] || { echo "no step $step defined" >&2; exit 1; }
"$fn"
