#!/usr/bin/env bash
# After a demo: suspend the traffic generator, stop the Gemma VM, optionally remove the load balancer.
# Usage: demo_down.sh [--teardown]     DRY_RUN=1 echoes every mutating command.
# The synthetic-data-feeder CronJob (56-feeder.yaml) is deliberately NOT suspended here: dashboards must stay fresh.
# Ends by confirming the CronJob is suspended and the Gemma VM is TERMINATED (fails loudly otherwise).
set -euo pipefail
. "$(dirname "$0")/_common.sh"
HERE="$(dirname "$0")"
TEARDOWN=0
case "${1:-}" in
  "") ;;
  --teardown) TEARDOWN=1 ;;
  *) die "usage: demo_down.sh [--teardown]" ;;
esac
guard_gcloud
guard_kube

if [ "$DRY_RUN" = "1" ]; then
  run kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":true}}'
elif kubectl -n "$NS" get cronjob glassbox-trafficgen >/dev/null 2>&1; then
  kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":true}}'
else
  echo "cronjob glassbox-trafficgen not found, skipping"
fi

# Stop Gemma only if it is running (stopping a stopped VM is harmless but slow to read).
VM_STATE="$(bash "$HERE/gemma.sh" status | sed 's/.*: //')"
if [ "$DRY_RUN" = "1" ] || [ "$VM_STATE" != "TERMINATED" ]; then
  bash "$HERE/gemma.sh" stop
fi

if [ "$TEARDOWN" = "1" ]; then
  bash "$HERE/teardown.sh"
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would confirm cronjob suspend=true and gemma TERMINATED"
  exit 0
fi
if kubectl -n "$NS" get cronjob glassbox-trafficgen >/dev/null 2>&1; then
  S="$(kubectl -n "$NS" get cronjob glassbox-trafficgen -o jsonpath='{.spec.suspend}')"
  [ "$S" = "true" ] || die "cronjob is not suspended (suspend=$S)"
  echo "cronjob glassbox-trafficgen: suspended"
fi
bash "$HERE/gemma.sh" status
[ "$(bash "$HERE/gemma.sh" status | sed 's/.*: //')" = "TERMINATED" ] || die "gemma VM is not TERMINATED"
echo "down: traffic generator suspended, gemma TERMINATED$([ "$TEARDOWN" = 1 ] && echo ', load balancer removed')"
