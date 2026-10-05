#!/usr/bin/env bash
# Idempotent: wait for both guardrail model deployments to start, set adaptive allocations
# (min 1 / max 2), then verify. Does not re-import models.
# PROJECT=observability (default) | security selects OBS_* or SEC_* from backend/.env. DRY_RUN=1 only prints the target.
set -euo pipefail
cd "$(dirname "$0")/../backend"
set -a; source .env; set +a
PROJECT="${PROJECT:-observability}"
case "$PROJECT" in
  observability) ES_URL="$OBS_ES_URL"; ES_KEY="$OBS_ES_ADMIN_KEY" ;;
  security)      ES_URL="${SEC_ES_URL:?SEC_ES_URL missing in backend/.env}"; ES_KEY="${SEC_ES_ADMIN_KEY:?SEC_ES_ADMIN_KEY missing in backend/.env}" ;;
  *) echo "PROJECT must be observability or security" >&2; exit 2 ;;
esac
if [[ "${DRY_RUN:-}" == "1" ]]; then echo "target project=$PROJECT host=$(echo "$ES_URL" | sed -E 's#^[a-z]+://([^/]+).*#\1#')"; exit 0; fi
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
auth=(-H "Authorization: ApiKey $ES_KEY")
stats() { curl --fail-with-body -sS "${auth[@]}" "$ES_URL/_ml/trained_models/$1/_stats"; }
for id in protectai__deberta-v3-base-prompt-injection-v2 elastic__distilbert-base-cased-finetuned-conll03-english; do
  state=""
  for _ in $(seq 1 120); do   # 120 x 5 s = 10 min
    state=$(stats "$id" | jq -r '.trained_model_stats[0].deployment_stats.state // "none"')
    [[ "$state" == "started" || "$state" == "fully_allocated" ]] && break
    sleep 5
  done
  if [[ "$state" != "started" && "$state" != "fully_allocated" ]]; then
    echo "TIMEOUT: $id deployment state is '$state' after 10 min" >&2; exit 1
  fi
  curl --fail-with-body -sS -X POST "$ES_URL/_ml/trained_models/$id/deployment/_update" \
    "${auth[@]}" -H 'Content-Type: application/json' \
    -d '{"adaptive_allocations":{"enabled":true,"min_number_of_allocations":1,"max_number_of_allocations":2}}' >/dev/null
  stats "$id" | jq -er --arg id "$id" '.trained_model_stats[0].deployment_stats
    | select(.adaptive_allocations.enabled == true and .adaptive_allocations.min_number_of_allocations == 1
             and .adaptive_allocations.max_number_of_allocations == 2)
    | "verified \($id): state=\(.state) adaptive_allocations=\(.adaptive_allocations)"' \
    || { echo "VERIFY FAILED: $id adaptive allocations not min1/max2" >&2; exit 1; }
done
