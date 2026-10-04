import pytest

from app.corpus_data import DOCS
from app.index_def import INDEX_BODY
from app.personas import PERSONAS, get_persona

ROLES = {"employee", "manager", "hr", "exec"}


def test_four_personas_with_unique_roles():
    assert {p.role for p in PERSONAS} == ROLES
    assert len({p.id for p in PERSONAS}) == 4


def test_unknown_persona_raises():
    with pytest.raises(KeyError):
        get_persona("intern")


def test_corpus_shape_and_tiers():
    assert len(DOCS) >= 20
    assert len({d["slug"] for d in DOCS}) == len(DOCS)
    for d in DOCS:
        assert set(d["allowed_roles"]) <= ROLES and d["allowed_roles"]
        assert d["classification"] in {"public", "internal", "confidential", "restricted"}
        assert len(d["content"]) > 60
    n = {r: sum(1 for d in DOCS if r in d["allowed_roles"]) for r in ROLES}
    assert n["employee"] < n["manager"] < n["hr"] < n["exec"]
    assert any(d["allowed_roles"] == ["exec"] for d in DOCS)


def test_index_maps_security_fields_as_keyword_and_semantic():
    props = INDEX_BODY["mappings"]["properties"]
    assert props["allowed_roles"]["type"] == "keyword"
    assert props["classification"]["type"] == "keyword"
    assert props["content_semantic"]["type"] == "semantic_text"
    assert props["content"]["copy_to"] == ["content_semantic"]
