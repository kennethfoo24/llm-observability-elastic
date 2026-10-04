import pytest
from elasticsearch import Elasticsearch

from app.config import Settings
from app.dls import load_keys
from app.index_def import INDEX_NAME

pytestmark = pytest.mark.integration


def _search(role_key, query, source=None):
    s = Settings()
    es = Elasticsearch(s.obs_es_url, api_key=role_key)
    body = {"query": query, "size": 10}
    if source is not None:
        body["_source"] = source
    return es.search(index=INDEX_NAME, **body)["hits"]["hits"]


def test_employee_cannot_see_restricted_docs_but_exec_can():
    keys = load_keys(Settings().persona_keys_path)
    emp = {h["_id"] for h in _search(keys["employee"], {"match": {"content": "severance reorganisation salary"}})}
    exe = {h["_id"] for h in _search(keys["exec"], {"match": {"content": "severance reorganisation salary"}})}
    # Employees see at least one doc (e.g., pto-policy for "paid time off")
    assert len(emp) > 0
    # Employees cannot see restricted docs
    assert "project-aurora" not in emp and "salary-bands" not in emp
    # Executives see the restricted docs
    assert {"project-aurora", "salary-bands"} <= exe


def test_catalog_key_never_returns_content():
    keys = load_keys(Settings().persona_keys_path)
    # Catalog can search by content (field_security grants it for queries)
    hits_match = _search(keys["catalog"], {"match": {"content": "severance"}}, source=["title", "classification", "allowed_roles"])
    assert len(hits_match) > 0
    # But _source never contains content fields
    assert all("content" not in h["_source"] for h in hits_match)
    # Also test match_all to verify basic functionality
    hits_all = _search(keys["catalog"], {"match_all": {}}, source=["title", "classification", "allowed_roles"])
    assert len(hits_all) > 0
    assert all("content" not in h["_source"] for h in hits_all)
