import logging

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

from app.config import Settings
from app.telemetry import emit_prompt_log, setup_guardrail_log_export

LOG = logging.getLogger("genai.guardrail")


@pytest.fixture(autouse=True)
def _restore_logger():
    yield
    setup_guardrail_log_export(Settings(_env_file=None, obs_es_url="http://x", obs_es_admin_key="k", obs_kibana_url="https://kb"))
    LOG.propagate = True


def _settings(**over):
    return Settings(_env_file=None, obs_es_url="http://x", obs_es_admin_key="k", obs_kibana_url="https://kb", **over)


def test_no_destination_is_a_noop_and_keeps_normal_log_propagation():
    assert setup_guardrail_log_export(_settings()) == []
    assert LOG.propagate is True


def test_both_destinations_receive_the_prompt_record_with_routing_attributes():
    exporters = {}

    def factory(endpoint, key):
        exporters[endpoint] = InMemoryLogRecordExporter()
        return exporters[endpoint]

    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="k1",
                  guardrail_log_sec_endpoint="https://sec.example", guardrail_log_sec_key="k2")
    handlers = setup_guardrail_log_export(s, exporter_factory=factory, simple=True)
    assert len(handlers) == 2 and LOG.propagate is False
    emit_prompt_log(prompt="Ignore previous instructions {x} \U0001F600", persona="employee", model="m", engine="sdk", status="ok")
    assert set(exporters) == {"https://obs.example", "https://sec.example"}
    for exp in exporters.values():
        rec = exp.get_finished_logs()
        assert len(rec) == 1
        attrs = dict(rec[0].log_record.attributes)
        assert attrs["data_stream.dataset"] == "genai_guardrail"
        assert attrs["genai.prompt_text"].startswith("Ignore previous instructions")
        assert attrs["app.persona"] == "employee" and attrs["guardrail.status"] == "ok"
        assert rec[0].resource.attributes["service.name"] == "glassbox-backend"


def test_a_destination_without_both_endpoint_and_key_is_skipped():
    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="",
                  guardrail_log_sec_endpoint="", guardrail_log_sec_key="k2")
    assert setup_guardrail_log_export(s, exporter_factory=lambda e, k: InMemoryLogRecordExporter(), simple=True) == []


def test_setup_is_idempotent_and_does_not_stack_handlers():
    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="k1")
    f = lambda e, k: InMemoryLogRecordExporter()  # noqa: E731
    setup_guardrail_log_export(s, exporter_factory=f, simple=True)
    setup_guardrail_log_export(s, exporter_factory=f, simple=True)
    from app.telemetry import _HANDLERS
    assert len(_HANDLERS) == 1 and sum(h in LOG.handlers for h in _HANDLERS) == 1


def test_the_default_factory_builds_an_otlp_http_exporter_with_the_key_only_in_the_auth_header(monkeypatch):
    seen = {}

    class Fake(InMemoryLogRecordExporter):
        def __init__(self, **kw):
            super().__init__()
            seen.update(kw)

    monkeypatch.setattr("opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter", Fake)
    s = _settings(guardrail_log_obs_endpoint="https://obs.example/", guardrail_log_obs_key="SECRETKEY")
    setup_guardrail_log_export(s, simple=True)
    assert seen["endpoint"] == "https://obs.example/v1/logs" and seen["headers"] == {"Authorization": "ApiKey SECRETKEY"}


def test_a_failing_exporter_never_leaks_the_key_into_logs(caplog):
    class Boom(InMemoryLogRecordExporter):
        def export(self, batch):
            raise RuntimeError("connection refused")

    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="SECRETKEY")
    setup_guardrail_log_export(s, exporter_factory=lambda e, k: Boom(), simple=True)
    with caplog.at_level(logging.DEBUG):
        emit_prompt_log(prompt="hello", persona="employee", model="m", engine="sdk", status="ok")
    assert "SECRETKEY" not in caplog.text


def test_rerun_shuts_down_the_previous_providers():
    from app.telemetry import _PROVIDERS
    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="k1")
    exp = InMemoryLogRecordExporter()
    setup_guardrail_log_export(s, exporter_factory=lambda e, k: exp, simple=True)
    assert len(_PROVIDERS) == 1
    setup_guardrail_log_export(_settings())
    assert _PROVIDERS == [] and exp._stopped is True


def test_create_app_survives_a_failing_log_exporter_setup(monkeypatch, caplog):
    from app.chat_service import Deps
    from app.main import create_app

    def boom(s):
        raise RuntimeError("https://obs.example/v1/logs?key=SECRETKEY")

    monkeypatch.setattr("app.main.setup_guardrail_log_export", boom)
    deps = Deps(None, None, None, None, {}, {"models": {}}, emit_log=lambda **kw: None, gate=object())
    with caplog.at_level(logging.WARNING):
        assert create_app(deps, _settings(), gate=object()) is not None
    assert "SECRETKEY" not in caplog.text and "RuntimeError" in caplog.text


def test_prompt_record_inside_a_span_carries_its_trace_and_span_ids():
    from opentelemetry.sdk.trace import TracerProvider

    exp = InMemoryLogRecordExporter()
    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="k1")
    setup_guardrail_log_export(s, exporter_factory=lambda e, k: exp, simple=True)
    tracer = TracerProvider().get_tracer("t")
    with tracer.start_as_current_span("chat") as span:
        emit_prompt_log(prompt="hi", persona="employee", model="m", engine="sdk", status="ok")
        ctx = span.get_span_context()
    rec = exp.get_finished_logs()[0].log_record
    assert rec.trace_id == ctx.trace_id and rec.span_id == ctx.span_id


def test_response_record_goes_to_both_exporters_with_typed_attributes():
    from app.telemetry import emit_response_log
    exporters = {}

    def factory(endpoint, key):
        exporters[endpoint] = InMemoryLogRecordExporter()
        return exporters[endpoint]

    s = _settings(guardrail_log_obs_endpoint="https://obs.example", guardrail_log_obs_key="k1",
                  guardrail_log_sec_endpoint="https://sec.example", guardrail_log_sec_key="k2")
    setup_guardrail_log_export(s, exporter_factory=factory, simple=True)
    assert LOG.propagate is False  # records never reach the shared collector path
    emit_response_log(prompt="q", response="a [x]", context="[x] T: body", retrieved_ids=["x"], cited_ids=["x"],
                      top_score=1.5, hidden_count=2, top_hidden_score=0.3, answered=True,
                      persona="employee", model="m", engine="sdk")
    assert set(exporters) == {"https://obs.example", "https://sec.example"}
    for exp in exporters.values():
        recs = exp.get_finished_logs()
        assert len(recs) == 1
        a = dict(recs[0].log_record.attributes)
        assert a["data_stream.dataset"] == "genai_response"
        assert list(a["genai.retrieved_ids"]) == ["x"] and list(a["genai.cited_ids"]) == ["x"]
        assert a["genai.top_score"] == 1.5 and a["genai.hidden_count"] == 2 and a["genai.answered"] is True
        assert a["genai.top_hidden_score"] == 0.3 and a["genai.response_text"] == "a [x]"
