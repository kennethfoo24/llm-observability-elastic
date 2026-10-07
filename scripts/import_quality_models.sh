#!/usr/bin/env bash
# Imports the sentiment and zero-shot models into the OBSERVABILITY project only (never Security), then sets
# adaptive allocations min 1 / max 2. Keys come from backend/.env (python scripts/make_env.py). DRY_RUN=1 prints the target.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../backend"
set -a; source .env; set +a
ES_URL="$OBS_ES_URL"; ES_KEY="$OBS_ES_ADMIN_KEY"
if [[ "${DRY_RUN:-}" == "1" ]]; then echo "target project=observability host=$(echo "$ES_URL" | sed -E 's#^[a-z]+://([^/]+).*#\1#')"; exit 0; fi
# The key never appears on a command line: docker gets `-e NAME` without a value (it reads the exported variable)
# and the container expands it; curl reads its header from a config on stdin.
export ES_URL ES_KEY
import() {  # $1=hub id  $2=task
  docker run --rm -e ES_URL -e ES_KEY --entrypoint sh docker.elastic.co/eland/eland:9.2.0 -c \
    'eland_import_hub_model --url "$ES_URL" --es-api-key "$ES_KEY" --hub-model-id "$1" --task-type "$2" --start --clear-previous --max-model-input-length 512' sh "$1" "$2"
}
import distilbert-base-uncased-finetuned-sst-2-english text_classification
import typeform/distilbert-base-uncased-mnli zero_shot_classification
for id in distilbert-base-uncased-finetuned-sst-2-english typeform__distilbert-base-uncased-mnli; do
  printf 'header = "Authorization: ApiKey %s"\n' "$ES_KEY" | curl -K - --fail-with-body -sS -X POST \
    "$ES_URL/_ml/trained_models/$id/deployment/_update" -H 'Content-Type: application/json' \
    -d '{"adaptive_allocations":{"enabled":true,"min_number_of_allocations":1,"max_number_of_allocations":2}}' >/dev/null
done
echo "imported and tuned the quality models in the observability project"
