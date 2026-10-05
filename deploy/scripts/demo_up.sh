#!/usr/bin/env bash
# Get ready for a demo: app running, traffic generator un-suspended, optionally Gemma started and awaited.
# Usage: demo_up.sh [--gemma]     DRY_RUN=1 echoes every mutating command.
# Prints the URL and a reminder where the password lives. It never prints the password.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
HERE="$(dirname "$0")"
GEMMA=0
case "${1:-}" in
  "") ;;
  --gemma) GEMMA=1 ;;
  *) die "usage: demo_up.sh [--gemma]" ;;
esac
guard_gcloud
guard_kube

if [ "$DRY_RUN" = "1" ]; then
  IP="${STATIC_IP:-$(static_ip 2>/dev/null || echo 0.0.0.0)}"
else
  IP="${STATIC_IP:-$(static_ip)}"
fi
HOST="$(host_for_ip "$IP")"

# App at one replica (a no-op if it already runs; teardown.sh scales it to 0).
run kubectl -n "$NS" scale deployment/glassbox --replicas=1
if [ "$DRY_RUN" != "1" ]; then
  kubectl -n "$NS" rollout status deployment/glassbox --timeout=300s
  kubectl -n "$NS" get ingress glassbox >/dev/null 2>&1 ||
    echo "warning: Ingress glassbox is missing (teardown.sh was run); re-create it with deploy/scripts/deploy.sh"
fi

# Traffic generator on (the one thing that costs money per hour while up).
if [ "$DRY_RUN" = "1" ]; then
  run kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":false}}'
elif kubectl -n "$NS" get cronjob glassbox-trafficgen >/dev/null 2>&1; then
  kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":false}}'
else
  echo "cronjob glassbox-trafficgen not found, skipping"
fi

if [ "$GEMMA" = "1" ]; then
  bash "$HERE/gemma.sh" start
  bash "$HERE/gemma.sh" wait
fi

if [ "$DRY_RUN" != "1" ]; then
  for _ in $(seq 1 20); do
    curl -fsS --max-time 10 "https://$HOST/healthz" >/dev/null 2>&1 && break
    sleep 6
  done
  curl -fsS --max-time 10 "https://$HOST/healthz" >/dev/null || die "https://$HOST/healthz did not answer"
fi
echo "ready: https://$HOST"
echo "password: see backend/secrets/app_password.txt (not printed here)"
[ "$GEMMA" = "1" ] || echo "gemma not started (add --gemma if the demo needs it; it costs about \$5-6 per hour)"
echo "when done: deploy/scripts/demo_down.sh"
