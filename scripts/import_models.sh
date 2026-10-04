#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
set -a; source .env; set +a
import() {  # $1=hub id  $2=task
  docker run --rm docker.elastic.co/eland/eland:latest eland_import_hub_model \
    --url "$OBS_ES_URL" --es-api-key "$OBS_ES_ADMIN_KEY" \
    --hub-model-id "$1" --task-type "$2" --start --clear-previous --max-model-input-length 512
}
import protectai/deberta-v3-base-prompt-injection-v2 text_classification
import elastic/distilbert-base-cased-finetuned-conll03-english ner
for id in protectai__deberta-v3-base-prompt-injection-v2 elastic__distilbert-base-cased-finetuned-conll03-english; do
  curl -sS -X POST "$OBS_ES_URL/_ml/trained_models/$id/deployment/_update" \
    -H "Authorization: ApiKey $OBS_ES_ADMIN_KEY" -H 'Content-Type: application/json' \
    -d '{"adaptive_allocations":{"enabled":true,"min_number_of_allocations":1,"max_number_of_allocations":2}}' >/dev/null
  echo "deployment updated: $id"
done
