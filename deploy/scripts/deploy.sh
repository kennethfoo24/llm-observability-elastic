#!/usr/bin/env bash
# Render and apply the manifests, wait for the rollout and the managed certificate, then check healthz.
# Usage: IMAGE=<image@digest> deploy/scripts/deploy.sh   (WITH_TRAFFICGEN=1 also applies the suspended CronJob;
# the synthetic-data-feeder CronJob deploy/k8s/56-feeder.yaml is always applied and NOT suspended)
# DRY_RUN=1 renders and echoes the apply instead of running it.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
cd "$(dirname "$0")/../.."
: "${IMAGE:?set IMAGE to the output of build_push.sh}"
guard_gcloud
[ "$DRY_RUN" = "1" ] || guard_kube

if [ "$DRY_RUN" = "1" ]; then IP="${STATIC_IP:-$(static_ip 2>/dev/null || echo 0.0.0.0)}"; else IP="${STATIC_IP:-$(static_ip)}"; fi
HOST="$(host_for_ip "$IP")"
FILES=(deploy/k8s/00-namespace.yaml deploy/k8s/10-serviceaccounts.yaml deploy/k8s/30-app.yaml deploy/k8s/40-ingress.yaml deploy/k8s/56-feeder.yaml)
[ "${WITH_TRAFFICGEN:-0}" = "1" ] && FILES+=(deploy/k8s/50-trafficgen.yaml)

RENDERED="$(python3 deploy/render.py "${FILES[@]}" --set IMAGE="$IMAGE" --set HOST="$HOST" \
  --set PROJECT="$PROJECT_ID" --set STATIC_IP_NAME="$STATIC_IP_NAME")"
if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] kubectl apply -f - (host=$HOST, files: ${FILES[*]})"
  exit 0
fi
printf '%s\n' "$RENDERED" | kubectl apply -f -
kubectl -n "$NS" rollout status deployment/glassbox --timeout=300s

status=""
for _ in $(seq 1 180); do   # 180 x 30 s = 90 minutes
  status="$(kubectl -n "$NS" get managedcertificate glassbox-cert -o jsonpath='{.status.certificateStatus}' 2>/dev/null || true)"
  echo "certificate status: ${status:-unknown}"
  [ "$status" = "Active" ] && break
  sleep 30
done
[ "$status" = "Active" ] || die "managed certificate is not Active (last status: ${status:-unknown})"
curl -fsS "https://$HOST/healthz" >/dev/null || die "https://$HOST/healthz failed"
echo "ok: https://$HOST"
