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

# ---- dispatch ---------------------------------------------------------------
step="${1:?usage: $0 <step-number>}"
fn="$(declare -F | awk '{print $3}' | grep -E "^step_${step}_" | head -1)"
[[ -n "$fn" ]] || { echo "no step $step defined" >&2; exit 1; }
"$fn"
