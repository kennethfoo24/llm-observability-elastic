#!/usr/bin/env bash
# Idempotent GCP bootstrap in project elastic-sa. DRY_RUN=1 only echoes the mutating commands.
# Creates only: Artifact Registry repo glassbox, global static IP glassbox-ip, service accounts
# glassbox-app (roles/aiplatform.user) and glassbox-monitoring (roles/monitoring.viewer) with
# Workload Identity bindings for namespace genai-demo. No service account keys are created.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
guard_gcloud
P=$PROJECT_ID

gcloud artifacts repositories describe glassbox --location="$REGION" --project="$P" >/dev/null 2>&1 \
  || run gcloud artifacts repositories create glassbox --repository-format=docker --location="$REGION" \
       --project="$P" --description="Glass Box demo images"

gcloud compute addresses describe "$STATIC_IP_NAME" --global --project="$P" >/dev/null 2>&1 \
  || run gcloud compute addresses create "$STATIC_IP_NAME" --global --project="$P"

for sa in glassbox-app glassbox-monitoring; do
  gcloud iam service-accounts describe "$sa@$P.iam.gserviceaccount.com" --project="$P" >/dev/null 2>&1 \
    || run gcloud iam service-accounts create "$sa" --display-name="$sa" --project="$P"
done

# add-iam-policy-binding is idempotent (an existing binding is left unchanged).
run gcloud projects add-iam-policy-binding "$P" \
  --member="serviceAccount:glassbox-app@$P.iam.gserviceaccount.com" --role=roles/aiplatform.user --condition=None
run gcloud projects add-iam-policy-binding "$P" \
  --member="serviceAccount:glassbox-monitoring@$P.iam.gserviceaccount.com" --role=roles/monitoring.viewer --condition=None
run gcloud iam service-accounts add-iam-policy-binding "glassbox-app@$P.iam.gserviceaccount.com" \
  --role=roles/iam.workloadIdentityUser --member="serviceAccount:$P.svc.id.goog[$NS/glassbox]" --project="$P"
run gcloud iam service-accounts add-iam-policy-binding "glassbox-monitoring@$P.iam.gserviceaccount.com" \
  --role=roles/iam.workloadIdentityUser --member="serviceAccount:$P.svc.id.goog[$NS/glassbox-monitoring]" --project="$P"

if IP="$(static_ip 2>/dev/null)" && [ -n "$IP" ]; then
  echo "static ip: $IP"; echo "host: $(host_for_ip "$IP")"
else
  echo "static ip: (not reserved yet; DRY_RUN=$DRY_RUN)"
fi
