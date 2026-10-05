import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from elasticsearch import Elasticsearch, NotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import Settings  # noqa: E402
from app.guardrail_pipeline import PIPELINE_ID, build_hook, build_pipeline  # noqa: E402

HOOK_PIPELINE = "logs@custom"   # confirmed in Phase 0
ap = argparse.ArgumentParser()
ap.add_argument("--project", choices=["observability", "security"], default="observability")
ap.add_argument("--print-target", action="store_true", help="print the target project and host, call nothing")
args = ap.parse_args()
s = Settings()
if args.project == "security":
    url, key = s.sec_es_url, s.sec_es_admin_key
else:
    url, key = s.obs_es_url, s.obs_es_admin_key
if args.print_target:
    print(f"target project={args.project} host={urlparse(url).netloc}")
    raise SystemExit(0)
es = Elasticsearch(url, api_key=key)
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
