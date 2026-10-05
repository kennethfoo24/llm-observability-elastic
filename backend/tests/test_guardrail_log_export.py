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
