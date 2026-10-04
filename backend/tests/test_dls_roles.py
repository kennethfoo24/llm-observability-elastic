from app.dls import CATALOG_ROLE_DESCRIPTOR, persona_role_descriptor


def test_persona_descriptor_filters_by_role_and_is_read_only():
    d = persona_role_descriptor("employee")["employee"]
    idx = d["indices"][0]
    assert idx["names"] == ["hr-kb"]
    assert idx["privileges"] == ["read"]
    assert idx["query"] == {"terms": {"allowed_roles": ["employee"]}}
    assert "monitor_inference" in d["cluster"]


def test_catalog_descriptor_only_grants_non_content_fields():
    idx = CATALOG_ROLE_DESCRIPTOR["catalog"]["indices"][0]
    assert set(idx["field_security"]["grant"]) == {"title", "classification", "allowed_roles"}
    assert "query" not in idx
