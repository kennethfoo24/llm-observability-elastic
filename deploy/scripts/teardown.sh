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
run kubectl -n "$NS" patch cronjob glassbox-trafficgen -p '{"spec":{"suspend":true}}' || true
run kubectl -n "$NS" scale deployment/glassbox --replicas=0

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
echo "static IP $STATIC_IP_NAME is kept (small cost); release it manually if wanted"
