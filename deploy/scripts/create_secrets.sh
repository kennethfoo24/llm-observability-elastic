#!/usr/bin/env bash
# Create/update the app Secrets in namespace genai-demo from gitignored local files ONLY:
#   backend/secrets/persona_keys.json, backend/secrets/guardrail_log_keys.json (keys obs, sec),
#   elasticsearch.txt, backend/secrets/app_password.txt (generated if missing).
# Env overrides: APP_PASSWORD, GEMMA_API_KEY, GLOG_OBS_KEY, GLOG_SEC_KEY.
# Values are never printed, only key NAMES. DRY_RUN=1 prints key names and target only.
# The guardrail log keys must be ingest-only keys (docs/dev-tools-mint-ingest-keys.md); the script
# refuses to fall back to the admin keys unless ALLOW_ADMIN_LOG_KEYS=1.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
cd "$(dirname "$0")/../.."
[ "${NAMESPACE:-$NS}" = "$NS" ] || die "namespace must be $NS"

APP_KEYS="obs_es_url kibana_url sec_kibana_url guardrail_key app_password gemma_api_key glog_obs_endpoint glog_obs_key glog_sec_endpoint glog_sec_key"
PERSONA_KEYS="persona_keys.json"

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] target: context=$KUBE_CONTEXT namespace=$NS"
  echo "[dry-run] secret glassbox-persona-keys keys: $PERSONA_KEYS"
  echo "[dry-run] secret glassbox-app keys: $APP_KEYS"
  exit 0
fi

guard_kube
guard_gcloud
[ -f backend/secrets/persona_keys.json ] || die "missing backend/secrets/persona_keys.json"
[ -f elasticsearch.txt ] || die "missing elasticsearch.txt"
# Load values into the environment without printing them.
eval "$(python3 - <<'PY'
import json, os, shlex
from pathlib import Path
raw = {}
for l in Path("elasticsearch.txt").read_text().splitlines():
    if "=" in l and " " not in l.split("=", 1)[0].strip():
        k, v = l.split("=", 1)
        raw[k.strip()] = v.strip()
keys = json.loads(Path("backend/secrets/persona_keys.json").read_text())
out = {
    "S_OBS_ES_URL": raw["OBSERVABILITY_ELASTICSEARCH"],
    "S_KIBANA_URL": raw["OBSERVABILITY_KIBANA"],
    "S_SEC_KIBANA_URL": raw.get("SECURITY_KIBANA", ""),
    "S_OBS_OTLP": raw["OBSERVABILITY_OPENTELEMETRY"],
    "S_SEC_OTLP": raw["SECURITY_OPENTELEMETRY"],
    "S_ADMIN_OBS": raw.get("OBSERVABILITY_API_KEY", ""),
    "S_ADMIN_SEC": raw.get("SECURITY_API_KEY", ""),
    "S_GUARDRAIL_KEY": keys["guardrail"],
}
gl = Path("backend/secrets/guardrail_log_keys.json")
if gl.is_file():
    g = json.loads(gl.read_text())
    out["S_FILE_OBS"] = g.get("obs", "")
    out["S_FILE_SEC"] = g.get("sec", "")
for k, v in out.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"

LOG_OBS_KEY="${GLOG_OBS_KEY:-${S_FILE_OBS:-}}"
LOG_SEC_KEY="${GLOG_SEC_KEY:-${S_FILE_SEC:-}}"
if [ -z "$LOG_OBS_KEY" ] || [ -z "$LOG_SEC_KEY" ]; then
  [ "${ALLOW_ADMIN_LOG_KEYS:-0}" = "1" ] || die "no ingest-only guardrail log keys: set GLOG_OBS_KEY/GLOG_SEC_KEY or fill backend/secrets/guardrail_log_keys.json (docs/dev-tools-mint-ingest-keys.md); ALLOW_ADMIN_LOG_KEYS=1 uses the admin keys instead (not recommended)"
  LOG_OBS_KEY="${LOG_OBS_KEY:-$S_ADMIN_OBS}"
  LOG_SEC_KEY="${LOG_SEC_KEY:-$S_ADMIN_SEC}"
fi

PW_FILE=backend/secrets/app_password.txt
if [ -z "${APP_PASSWORD:-}" ]; then
  if [ ! -s "$PW_FILE" ]; then
    (umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(18))" > "$PW_FILE")
    echo "generated a demo password in $PW_FILE (read it there; never printed here)"
  fi
  APP_PASSWORD="$(cat "$PW_FILE")"
fi
if [ -z "${GEMMA_API_KEY:-}" ]; then
  # Read-only describe of the existing VM metadata; the value is captured, never printed.
  GEMMA_API_KEY="$(gcloud compute instances describe kenneth-gemma-llm --zone asia-southeast1-c --project "$PROJECT_ID" --format=json \
    | python3 -c "import json,sys; print(next(i['value'] for i in json.load(sys.stdin)['metadata']['items'] if i['key']=='vllm-api-key'))")"
fi

kubectl apply -f deploy/k8s/00-namespace.yaml >/dev/null
kubectl -n "$NS" create secret generic glassbox-persona-keys --from-file=persona_keys.json=backend/secrets/persona_keys.json \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
# Values go through a mode-600 temp env file (never argv, so they cannot show up in ps).
ENVF="$(umask 077; mktemp "${TMPDIR:-/tmp}/glassbox-secret.XXXXXX")"
trap 'rm -f "$ENVF"' EXIT
{
  printf 'obs_es_url=%s\n' "$S_OBS_ES_URL"
  printf 'kibana_url=%s\n' "$S_KIBANA_URL"
  printf 'sec_kibana_url=%s\n' "$S_SEC_KIBANA_URL"
  printf 'guardrail_key=%s\n' "$S_GUARDRAIL_KEY"
  printf 'app_password=%s\n' "$APP_PASSWORD"
  printf 'gemma_api_key=%s\n' "$GEMMA_API_KEY"
  printf 'glog_obs_endpoint=%s\n' "$S_OBS_OTLP"
  printf 'glog_obs_key=%s\n' "$LOG_OBS_KEY"
  printf 'glog_sec_endpoint=%s\n' "$S_SEC_OTLP"
  printf 'glog_sec_key=%s\n' "$LOG_SEC_KEY"
} > "$ENVF"
kubectl -n "$NS" create secret generic glassbox-app --from-env-file="$ENVF" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "secrets applied in $NS: glassbox-persona-keys ($PERSONA_KEYS); glassbox-app ($APP_KEYS)"
