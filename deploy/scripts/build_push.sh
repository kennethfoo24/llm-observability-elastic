#!/usr/bin/env bash
# Build the amd64 image in Cloud Build and print the immutable reference (image@digest).
# DRY_RUN=1 prints the build command and the config it would submit; nothing is built.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
cd "$(dirname "$0")/../.."
guard_gcloud
TAG="$(git rev-parse --short HEAD)"
IMAGE_BASE="$REGION-docker.pkg.dev/$PROJECT_ID/glassbox/app"
CFG="$(mktemp "${TMPDIR:-/tmp}/cloudbuild.glassbox.XXXXXX")"
trap 'rm -f "$CFG"' EXIT
cat > "$CFG" <<YAML
steps:
  - name: gcr.io/cloud-builders/docker
    args: ["build", "--platform", "linux/amd64", "-f", "backend/Dockerfile", "-t", "$IMAGE_BASE:$TAG", "."]
images: ["$IMAGE_BASE:$TAG"]
YAML
# .gcloudignore keeps elasticsearch.txt, .env and secrets out of the uploaded build context.
run gcloud builds submit --project="$PROJECT_ID" --config="$CFG" --region="$REGION" .
if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would print $IMAGE_BASE@<digest>"
else
  DIGEST="$(gcloud artifacts docker images describe "$IMAGE_BASE:$TAG" --project="$PROJECT_ID" --format='value(image_summary.digest)')"
  echo "$IMAGE_BASE@$DIGEST"
fi
