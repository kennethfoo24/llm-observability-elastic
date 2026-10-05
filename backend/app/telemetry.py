import logging

from opentelemetry import trace

_log = logging.getLogger("genai.guardrail")
_log.setLevel(logging.INFO)


def trace_id_hex() -> str:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else ""


def set_root_attrs(**attrs) -> None:
    span = trace.get_current_span()
    for k, v in attrs.items():
        span.set_attribute(k.replace("__", "."), v)


def emit_prompt_log(*, prompt: str, persona: str, model: str, engine: str, status: str) -> None:
    _log.info("genai prompt", extra={
        "data_stream.dataset": "genai_guardrail",
        "genai.prompt_text": prompt,
        "app.persona": persona,
        "app.genai.model": model,
        "app.genai.engine": engine,
        "guardrail.status": status,
    })


_HANDLERS: list[logging.Handler] = []
_PROVIDERS: list = []


def setup_guardrail_log_export(s, exporter_factory=None, simple: bool = False) -> list[logging.Handler]:
    """Send guardrail prompt log records straight to the managed OTLP endpoints (Observability and Security).

    The shared in-cluster log path writes to a fixed `logs.otel` index, so dataset routing and the guardrail
    ingest pipeline would never run there; these records therefore bypass it (propagate=False)."""
    from opentelemetry.exporter.otlp.proto.http import _log_exporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, SimpleLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

    for h in _HANDLERS:
        _log.removeHandler(h)
    _HANDLERS.clear()
    for p in _PROVIDERS:
        try:
            p.shutdown()
        except Exception:  # noqa: BLE001 - never let telemetry teardown raise
            pass
    _PROVIDERS.clear()
    factory = exporter_factory or (lambda endpoint, key: _log_exporter.OTLPLogExporter(
        endpoint=endpoint.rstrip("/") + "/v1/logs", headers={"Authorization": f"ApiKey {key}"}))
    for endpoint, key in ((s.guardrail_log_obs_endpoint, s.guardrail_log_obs_key),
                          (s.guardrail_log_sec_endpoint, s.guardrail_log_sec_key)):
        if not endpoint or not key:
            continue
        provider = LoggerProvider(resource=Resource.create(
            {"service.name": "glassbox-backend", "deployment.environment": "demo"}))
        processor_cls = SimpleLogRecordProcessor if simple else BatchLogRecordProcessor
        provider.add_log_record_processor(processor_cls(factory(endpoint, key)))
        handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
        _log.addHandler(handler)
        _PROVIDERS.append(provider)
        _HANDLERS.append(handler)
    _log.propagate = not _HANDLERS
    return list(_HANDLERS)
