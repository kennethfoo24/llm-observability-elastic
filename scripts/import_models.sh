#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../backend"
set -a; source .env; set +a
import() {  # $1=hub id  $2=task
  docker run --rm docker.elastic.co/eland/eland:9.2.0 eland_import_hub_model \
    --url "$OBS_ES_URL" --es-api-key "$OBS_ES_ADMIN_KEY" \
    --hub-model-id "$1" --task-type "$2" --start --clear-previous --max-model-input-length 512
}
import protectai/deberta-v3-base-prompt-injection-v2 text_classification
import elastic/distilbert-base-cased-finetuned-conll03-english ner
"$HERE/update_deployments.sh"
