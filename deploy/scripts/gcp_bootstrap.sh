#!/usr/bin/env bash
# Idempotent GCP bootstrap in project elastic-sa. DRY_RUN=1 only echoes the mutating commands.
# Creates only: Artifact Registry repo glassbox and global static IP glassbox-ip. The LLM is the Elastic
# Inference Service (reached with an Elastic API key), so no GCP service accounts or IAM roles are needed.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
guard_gcloud
P=$PROJECT_ID

gcloud artifacts repositories describe glassbox --location="$REGION" --project="$P" >/dev/null 2>&1 \
  || run gcloud artifacts repositories create glassbox --repository-format=docker --location="$REGION" \
       --project="$P" --description="LLM Observability demo images"

gcloud compute addresses describe "$STATIC_IP_NAME" --global --project="$P" >/dev/null 2>&1 \
  || run gcloud compute addresses create "$STATIC_IP_NAME" --global --project="$P"

if IP="$(static_ip 2>/dev/null)" && [ -n "$IP" ]; then
  echo "static ip: $IP"; echo "host: $(host_for_ip "$IP")"
else
  echo "static ip: (not reserved yet; DRY_RUN=$DRY_RUN)"
fi
