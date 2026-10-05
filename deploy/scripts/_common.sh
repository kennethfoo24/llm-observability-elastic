#!/usr/bin/env bash
# Shared guards and helpers. Sourced by every script in this directory.
# DRY_RUN=1 echoes mutating commands instead of running them.
set -euo pipefail

PROJECT_ID=elastic-sa
REGION=asia-southeast1
ZONE=asia-southeast1-a
CLUSTER=kenneth-gke
KUBE_CONTEXT="gke_${PROJECT_ID}_${ZONE}_${CLUSTER}"
NS=genai-demo
STATIC_IP_NAME=glassbox-ip
DRY_RUN="${DRY_RUN:-0}"

die() { echo "error: $*" >&2; exit 1; }

case "$DRY_RUN" in 0|1) ;; *) die "DRY_RUN must be 0 or 1, got '$DRY_RUN'" ;; esac

# Print and (unless DRY_RUN=1) run a mutating command.
run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '[dry-run]'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

# Read-only commands always run.
guard_gcloud() {
  local p
  p="$(gcloud config get-value project 2>/dev/null || true)"
  [ "$p" = "$PROJECT_ID" ] || die "gcloud project is '$p', expected $PROJECT_ID (run: gcloud config set project $PROJECT_ID)"
}

guard_kube() {
  local c
  c="$(kubectl config current-context 2>/dev/null || true)"
  [ "$c" = "$KUBE_CONTEXT" ] || die "kube context is '$c', expected $KUBE_CONTEXT"
}

static_ip() {
  gcloud compute addresses describe "$STATIC_IP_NAME" --global --project="$PROJECT_ID" --format='value(address)'
}

host_for_ip() { local ip="$1"; echo "${ip//./-}.sslip.io"; }
