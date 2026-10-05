#!/usr/bin/env bash
# Stop the cost: delete the Ingress and its LB objects, scale the app to 0. Everything is in genai-demo.
# --all additionally deletes the namespace, after the literal confirmation "delete genai-demo".
# DRY_RUN=1 echoes the commands only.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
guard_gcloud
guard_kube
ALL=0
[ "${1:-}" = "--all" ] && ALL=1

run kubectl -n "$NS" delete ingress glassbox --ignore-not-found
run kubectl -n "$NS" delete managedcertificate glassbox-cert --ignore-not-found
run kubectl -n "$NS" delete backendconfig glassbox --ignore-not-found
run kubectl -n "$NS" delete frontendconfig glassbox --ignore-not-found
# Suspend the CronJob; only "not found" (never deployed) is tolerated.
if [ "$DRY_RUN" = "1" ]; then
  run kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":true}}'
elif kubectl -n "$NS" get cronjob glassbox-trafficgen >/dev/null 2>&1; then
  kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":true}}'
else
  echo "cronjob glassbox-trafficgen not found, skipping"
fi
run kubectl -n "$NS" scale deployment/glassbox --replicas=0
# The Vertex AI agent costs almost nothing but is stopped too (only if deployed).
if [ "$DRY_RUN" = "1" ] || kubectl -n "$NS" get deployment glassbox-elastic-agent >/dev/null 2>&1; then
  run kubectl -n "$NS" scale deployment/glassbox-elastic-agent --replicas=0
fi
run kubectl -n "$NS" wait --for=delete pod -l app=glassbox --timeout=180s

if [ "$ALL" = "1" ]; then
  echo "This will delete namespace $NS and everything in it:"
  kubectl -n "$NS" get all,secrets,cronjobs 2>/dev/null || true
  if [ "$DRY_RUN" = "1" ]; then
    run kubectl delete namespace "$NS"
  else
    read -r -p 'Type "delete genai-demo" to confirm: ' ans
    [ "$ans" = "delete genai-demo" ] || die "not confirmed"
    kubectl delete namespace "$NS"
  fi
fi
echo "stopped: ingress removed, app scaled to 0 and pods gone (dry-run: DRY_RUN=$DRY_RUN)"
echo "static IP $STATIC_IP_NAME is kept (small cost); release it manually if wanted"
