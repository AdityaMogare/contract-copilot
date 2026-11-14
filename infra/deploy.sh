#!/usr/bin/env bash
# Build → push → roll a new Container Apps revision (design 02 §5A).
# Usage: ./infra/deploy.sh          (deploys the current commit; refuses if the tree is dirty)
# The image tag is the git commit, so every revision maps to exact source. Never "latest".
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] && set -a && source .env && set +a
SFX="${SFX:?set SFX in .env}"
RG="rg-contract-copilot"; ACR="acr$SFX"; CA="ca-copilot-$SFX"

if [[ -n "$(git status --porcelain -- app pyproject.toml uv.lock Dockerfile)" ]]; then
  echo "Uncommitted changes in app code: commit first so the image tag matches the source." >&2
  exit 1
fi
TAG="$(git rev-parse --short HEAD)"
IMAGE="$ACR.azurecr.io/copilot:$TAG"

# amd64: Container Apps runs amd64; this Mac is arm64 (an arm64 image fails with "exec format error").
docker buildx build --platform linux/amd64 -t "$IMAGE" --load .
az acr login -n "$ACR"            # my Entra token → ACR refresh token (POST /oauth2/exchange)
docker push "$IMAGE"
# A new revision pulls the image with the app's managed identity (AcrPull).
az containerapp update -g "$RG" -n "$CA" --image "$IMAGE" -o none
az containerapp revision list -g "$RG" -n "$CA" \
  --query "[?properties.active].{revision:name, image:properties.template.containers[0].image, health:properties.healthState, traffic:properties.trafficWeight}" -o table
