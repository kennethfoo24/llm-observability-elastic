import sys
from pathlib import Path

from elasticsearch import Elasticsearch, NotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import Settings  # noqa: E402
from app.guardrail_pipeline import PIPELINE_ID, build_hook, build_pipeline  # noqa: E402

HOOK_PIPELINE = "logs@custom"   # confirmed in Phase 0
s = Settings()
es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
es.ingest.put_pipeline(id=PIPELINE_ID, **build_pipeline())
try:
    existing = es.ingest.get_pipeline(id=HOOK_PIPELINE)[HOOK_PIPELINE]
except NotFoundError:
    existing = None
if existing:  # GET returns read-only metadata (created_date_millis, ...); PUT rejects them
    existing = {k: v for k, v in existing.items()
                if k not in ("created_date_millis", "modified_date_millis")
                and not (k.startswith("_") and k != "_meta")}
es.ingest.put_pipeline(id=HOOK_PIPELINE, **build_hook(existing))
print("installed", PIPELINE_ID, "and hooked it into", HOOK_PIPELINE)
