#!/bin/sh
# Deploy wrapper for the GCP VM: pull secrets from Secret Manager, then run
# docker compose with them in the environment (compose interpolates ${VAR} and
# never sees a plaintext file).
#
#   ./deploy.sh                # up -d   (default)
#   ./deploy.sh down
#   ./deploy.sh logs -f backend
#   ./deploy.sh up -d --build
#
# ALWAYS deploy through this script. Running `docker compose -f
# docker-compose.deploy.yml ...` directly starts the stack with blank secrets
# and the backend refuses to boot.
set -e
cd "$(dirname "$0")"

. ./secrets.sh

exec sudo env \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  HF_API_TOKEN="$HF_API_TOKEN" \
  HF_TOKEN="$HF_TOKEN" \
  APP_SECRET_KEY="$APP_SECRET_KEY" \
  POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  docker compose -f docker-compose.deploy.yml "${@:-up -d}"
