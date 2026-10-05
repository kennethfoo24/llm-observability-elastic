#!/usr/bin/env bash
# Operate the self-hosted Gemma VM: gemma.sh start|stop|status|wait
# The VM (A100) costs about $5-6 per hour while running and powers itself off 180 minutes after boot.
# `wait` polls the vLLM /v1/models URL every 15 s (up to 15 minutes) with the Bearer key read from the VM
# metadata into memory only. The key is never printed, never put on a command line and never traced.
# DRY_RUN=1 echoes start/stop/wait instead of running them; status is read-only and always runs.
set -euo pipefail
. "$(dirname "$0")/_common.sh"

VM=kenneth-gemma-llm
VM_ZONE=asia-southeast1-c
MODELS_URL="https://llm-34-126-172-79.nip.io/v1/models"
POLL_S=15
MAX_S=900

guard_gcloud

vm_status() {
  gcloud compute instances describe "$VM" --zone="$VM_ZONE" --project="$PROJECT_ID" --format='value(status)'
}

cmd_status() {
  echo "vm $VM ($VM_ZONE): $(vm_status)"
}

cmd_start() {
  echo "COST WARNING: $VM costs about \$5-6 per hour while running. It shuts itself down 180 minutes after boot (started $(date -u +%H:%M)Z); stop it yourself with: gemma.sh stop"
  run gcloud compute instances start "$VM" --zone="$VM_ZONE" --project="$PROJECT_ID"
}

cmd_stop() {
  run gcloud compute instances stop "$VM" --zone="$VM_ZONE" --project="$PROJECT_ID"
}

cmd_wait() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] would poll $MODELS_URL every ${POLL_S}s up to ${MAX_S}s with the key from VM metadata (not printed)"
    return 0
  fi
  local key
  key="$(gcloud compute instances describe "$VM" --zone="$VM_ZONE" --project="$PROJECT_ID" \
    --format='value(metadata.items.filter(key:vllm-api-key).extract(value).flatten())' 2>/dev/null || true)"
  [ -n "$key" ] || die "vllm-api-key metadata not readable on $VM"
  local t0=$SECONDS code elapsed
  while :; do
    # The header goes to curl through a config on stdin (not argv); -s hides errors and the header.
    code="$(printf 'header = "Authorization: Bearer %s"\n' "$key" |
      curl -s -K - -o /dev/null -w '%{http_code}' --max-time 10 "$MODELS_URL" 2>/dev/null || true)"
    elapsed=$((SECONDS - t0))
    echo "elapsed ${elapsed}s: HTTP ${code:-000}"
    if [ "$code" = "200" ]; then
      echo "gemma ready after ${elapsed}s"
      return 0
    fi
    [ "$elapsed" -lt "$MAX_S" ] || die "gemma not ready after ${MAX_S}s"
    sleep "$POLL_S"
  done
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  wait) cmd_wait ;;
  *) die "usage: gemma.sh start|stop|status|wait" ;;
esac
