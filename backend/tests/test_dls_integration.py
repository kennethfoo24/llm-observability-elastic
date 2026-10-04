import pytest
from elasticsearch import Elasticsearch

from app.config import Settings
from app.dls import load_keys

pytestmark = pytest.mark.integration


def _search(role_key, text):
    s = Settings()
    es = Elasticsearch(s.obs_es_url, api_key=role_key)
    return es.search(index="hr-kb", query={"match": {"content": text}}, size=10)["hits"]["hits"]


def test_employee_cannot_see_restricted_docs_but_exec_can():
    keys = load_keys(Settings().persona_keys_path)
    emp = {h["_id"] for h in _search(keys["employee"], "severance reorganisation salary")}
    exe = {h["_id"] for h in _search(keys["exec"], "severance reorganisation salary")}
    assert "project-aurora" not in emp and "salary-bands" not in emp
    assert {"project-aurora", "salary-bands"} <= exe


def test_catalog_key_never_returns_content():
    keys = load_keys(Settings().persona_keys_path)
    hits = _search(keys["catalog"], "severance")
    assert hits and all("content" not in h["_source"] for h in hits)
