import sys
from pathlib import Path

from elasticsearch import Elasticsearch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from app.config import Settings  # noqa: E402

s = Settings()
es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
role = {"p0-probe": {"cluster": ["monitor_inference"], "indices": [{
    "names": ["hr-kb"], "privileges": ["read"],
    "query": {"terms": {"allowed_roles": ["employee"]}}}]}}
try:
    resp = es.security.create_api_key(name="p0-probe", role_descriptors=role, expiration="1h")
    print("CREATE OK id=", resp["id"])
    es.security.invalidate_api_key(ids=[resp["id"]])
    print("invalidated")
except Exception as e:  # noqa: BLE001
    print("CREATE FAILED:", type(e).__name__, str(e)[:300])
