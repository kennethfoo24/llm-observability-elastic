from app.envfile import parse_env_text, to_app_env

TEXT = """Elastic Security Serverless Project
SECURITY_ELASTICSEARCH=https://sec.es.example 
SECURITY_API_KEY=sec-key
OBSERVABILITY_ELASTICSEARCH=https://obs.es.example
OBSERVABILITY_KIBANA=https://obs.kb.example
OBSERVABILITY_OPENTELEMETRY=https://obs.ingest.example
OBSERVABILITY_API_KEY=obs-key
"""


def test_parse_ignores_headings_and_trims_whitespace():
    raw = parse_env_text(TEXT)
    assert raw["SECURITY_ELASTICSEARCH"] == "https://sec.es.example"
    assert "Elastic Security Serverless Project" not in raw


def test_to_app_env_maps_names():
    env = to_app_env(parse_env_text(TEXT))
    assert env["OBS_ES_URL"] == "https://obs.es.example"
    assert env["OBS_ES_ADMIN_KEY"] == "obs-key"
    assert env["OBS_KIBANA_URL"] == "https://obs.kb.example"
    assert env["OBS_OTLP_URL"] == "https://obs.ingest.example"
    assert env["SEC_ES_URL"] == "https://sec.es.example"
    assert env["SEC_ES_ADMIN_KEY"] == "sec-key"
