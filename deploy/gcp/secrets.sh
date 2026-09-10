#!/bin/sh
# Fetch deploy secrets from GCP Secret Manager into the environment.
# Sourced by deploy.sh on the VM. Values are never written to disk.
#
#   . ./secrets.sh        # note the leading dot — must run in the current shell
#
# Requires: the VM's service account has roles/secretmanager.secretAccessor and
# the instance has the cloud-platform access scope (see DEPLOY.md § 3.1).
set -e

PROJ="${GCP_PROJECT:-candidate-screener-2c4010f0}"

_t=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

_g() {
  curl -s -H "Authorization: Bearer $_t" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJ/secrets/$1/versions/latest:access" \
    | python3 -c "import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())"
}

export OPENAI_API_KEY=$(_g candidate-openai-api-key)
export HF_API_TOKEN=$(_g candidate-hf-token)
export HF_TOKEN=$HF_API_TOKEN                       # app accepts either name
export APP_SECRET_KEY=$(_g candidate-app-secret-key)
export POSTGRES_PASSWORD=$(_g candidate-postgres-password)

echo "secrets loaded (${#OPENAI_API_KEY}/${#HF_TOKEN}/${#APP_SECRET_KEY}/${#POSTGRES_PASSWORD} chars)"
