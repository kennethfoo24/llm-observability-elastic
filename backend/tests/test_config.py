from app.config import Settings


def test_defaults_and_overrides(monkeypatch):
    monkeypatch.setenv("OBS_ES_URL", "https://obs.es.example")
    monkeypatch.setenv("OBS_ES_ADMIN_KEY", "k")
    monkeypatch.setenv("OBS_KIBANA_URL", "https://obs.kb.example")
    s = Settings(_env_file=None)
    assert s.vertex_project == "elastic-sa"
    assert s.index_name == "hr-kb"
    assert s.gemma_model_id == "google/gemma-4-31B-it"
    assert s.max_message_chars == 4000
    assert s.guardrail_timeout_s == 1.5


def test_guardrail_key_falls_back_to_admin_key_until_a_scoped_key_is_set(monkeypatch):
    monkeypatch.setenv("OBS_ES_URL", "https://obs.es.example")
    monkeypatch.setenv("OBS_ES_ADMIN_KEY", "admin")
    monkeypatch.setenv("OBS_KIBANA_URL", "https://obs.kb.example")
    s = Settings(_env_file=None)
    assert s.obs_es_guardrail_key == "" and s.guardrail_es_key == "admin"
    s = Settings(_env_file=None, obs_es_guardrail_key="scoped")
    assert s.guardrail_es_key == "scoped"
