import sys
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import Settings  # noqa: E402
from app.corpus_data import DOCS  # noqa: E402
from app.index_def import INDEX_BODY, INDEX_NAME  # noqa: E402

s = Settings()
es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key, request_timeout=120)
if es.indices.exists(index=INDEX_NAME):
    es.indices.delete(index=INDEX_NAME)
es.indices.create(index=INDEX_NAME, **INDEX_BODY)
helpers.bulk(es, ({"_index": INDEX_NAME, "_id": d["slug"],
                   "_source": {k: d[k] for k in ("title", "classification", "allowed_roles", "content")}}
                  for d in DOCS), refresh="wait_for")
print("indexed", es.count(index=INDEX_NAME)["count"], "docs into", INDEX_NAME)
