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
