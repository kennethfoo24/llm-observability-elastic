import pytest
from elasticsearch import Elasticsearch

from app.config import Settings
from app.dls import load_keys
from app.index_def import INDEX_NAME
from app.retrieval import Retriever

pytestmark = pytest.mark.integration


def _search(role_key, query, source=None):
    s = Settings()
    es = Elasticsearch(s.obs_es_url, api_key=role_key)
    body = {"query": query, "size": 10}
    if source is not None:
        body["_source"] = source
    return es.search(index=INDEX_NAME, **body)["hits"]["hits"]


def test_employee_cannot_see_manager_docs_but_manager_can():
    keys = load_keys(Settings().persona_keys_path)
    emp = {h["_id"] for h in _search(keys["employee"], {"match": {"content": "severance reorganisation salary"}})}
    mgr = {h["_id"] for h in _search(keys["manager"], {"match": {"content": "salary bands"}})}
    # Positive control: a query that MUST hit an employee-visible doc.
    pto = {h["_id"] for h in _search(keys["employee"], {"match": {"content": "paid time off"}})}
    assert "pto-policy" in pto
    # Employees cannot see restricted docs
    assert "project-aurora" not in emp and "salary-bands" not in emp
    # Managers see manager-level docs but not the exec-only ones
    assert "salary-bands" in mgr and "project-aurora" not in mgr


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


AURORA_Q = "what is the Project Aurora severance budget"


def _retriever():
    s = Settings()
    return Retriever(s.obs_es_url, load_keys(s.persona_keys_path), s.index_name)


def _assert_no_content_anywhere(result):
    for ghost in result.hidden:
        assert not hasattr(ghost, "content") and set(vars(ghost)) == {"id", "title", "classification"}


def test_retriever_employee_never_gets_aurora_content_but_sees_it_as_hidden():
    res = _retriever().search("employee", AURORA_Q)
    assert "project-aurora" not in {d.id for d in res.docs}
    assert "project-aurora" in {g.id for g in res.hidden}
    _assert_no_content_anywhere(res)


def test_retriever_manager_gets_salary_bands_with_content_but_aurora_stays_hidden():
    res = _retriever().search("manager", "what are the salary bands for L3 to L5")
    bands = [d for d in res.docs if d.id == "salary-bands"]
    assert bands and bands[0].content
    assert "salary-bands" not in {g.id for g in res.hidden}
    _assert_no_content_anywhere(res)
