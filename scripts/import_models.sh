#!/usr/bin/env bash
# PROJECT=observability (default) | security selects OBS_* or SEC_* from backend/.env. DRY_RUN=1 only prints the target.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../backend"
set -a; source .env; set +a
PROJECT="${PROJECT:-observability}"
case "$PROJECT" in
  observability) ES_URL="$OBS_ES_URL"; ES_KEY="$OBS_ES_ADMIN_KEY" ;;
  security)      ES_URL="${SEC_ES_URL:?SEC_ES_URL missing in backend/.env}"; ES_KEY="${SEC_ES_ADMIN_KEY:?SEC_ES_ADMIN_KEY missing in backend/.env}" ;;
  *) echo "PROJECT must be observability or security" >&2; exit 2 ;;
esac
export PROJECT
if [[ "${DRY_RUN:-}" == "1" ]]; then echo "target project=$PROJECT host=$(echo "$ES_URL" | sed -E 's#^[a-z]+://([^/]+).*#\1#')"; exit 0; fi
import() {  # $1=hub id  $2=task
  docker run --rm docker.elastic.co/eland/eland:9.2.0 eland_import_hub_model \
    --url "$ES_URL" --es-api-key "$ES_KEY" \
    --hub-model-id "$1" --task-type "$2" --start --clear-previous --max-model-input-length 512
}
import protectai/deberta-v3-base-prompt-injection-v2 text_classification
import elastic/distilbert-base-cased-finetuned-conll03-english ner
"$HERE/update_deployments.sh"
