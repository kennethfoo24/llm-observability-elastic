import json

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import Settings
from app.llm_eis import EisClient, EisError
from app.models import get_models


@pytest.fixture
def s(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://es.example", "OBS_ES_ADMIN_KEY": "adminkey", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


@pytest.fixture
def spans(monkeypatch):
    exp = InMemorySpanExporter()
    prov = TracerProvider()
    prov.add_span_processor(SimpleSpanProcessor(exp))
    monkeypatch.setattr("app.llm_eis.tracer", prov.get_tracer("t"))
    return exp


def sse(*chunks, bom=True):
    out = ""
    for c in chunks:
        out += ("﻿" if bom else "") + "event: message\ndata: " + (c if isinstance(c, str) else json.dumps(c)) + "\n\n"
    return out.encode()


def _chunks():
    return [
        {"choices": [{"delta": {"role": "assistant", "content": "18 days "}, "index": 0}], "model": "openai-gpt-5.4-mini"},
        {"choices": [{"delta": {"content": "[pto]"}, "index": 0}], "model": "openai-gpt-5.4-mini"},
        {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}], "model": "openai-gpt-5.4-mini",
         "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}},
        "[DONE]",
    ]


def _client(s, body=None, status=200, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, content=body if body is not None else sse(*_chunks()))
    return EisClient(s, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_aggregates_stream_into_text_usage_and_response_model(s, spans):
    seen = []
    r = _client(s, seen=seen).chat(get_models(s)["eis-gpt-mini"], "sys", "user q")
    assert (r.text, r.input_tokens, r.output_tokens, r.response_model) == ("18 days [pto]", 120, 30, "openai-gpt-5.4-mini")
    req = seen[0]
    assert req.url.path == "/_inference/chat_completion/.openai-gpt-5.4-mini-chat_completion/_stream"
    assert req.headers["authorization"] == "ApiKey adminkey"
    body = json.loads(req.content)
    assert body == {"messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "user q"}],
                    "max_completion_tokens": s.eis_max_tokens}


def test_uses_guardrail_key_when_set(s, spans):
    s2 = s.model_copy(update={"obs_es_guardrail_key": "guardkey"})
    seen = []
    _client(s2, seen=seen).chat(get_models(s2)["eis-gpt-mini"], "a", "b")
    assert seen[0].headers["authorization"] == "ApiKey guardkey"


def test_genai_span_attributes(s, spans, monkeypatch):
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "SPAN_ONLY")
    _client(s).chat(get_models(s)["eis-gpt-mini"], "sys", "user q")
    sp = spans.get_finished_spans()[0]
    a = sp.attributes
    assert sp.name == "chat gpt-5.4-mini" and sp.kind == trace.SpanKind.CLIENT
    assert a["gen_ai.operation.name"] == "chat" and a["gen_ai.provider.name"] == "elastic"
    assert a["gen_ai.request.model"] == "gpt-5.4-mini" and a["gen_ai.response.model"] == "openai-gpt-5.4-mini"
    assert a["gen_ai.usage.input_tokens"] == 120 and a["gen_ai.usage.output_tokens"] == 30
    assert a["gen_ai.request.max_tokens"] == s.eis_max_tokens
    assert json.loads(a["gen_ai.input.messages"]) == [{"role": "user", "parts": [{"type": "text", "content": "user q"}]}]
    assert json.loads(a["gen_ai.system_instructions"]) == [{"type": "text", "content": "sys"}]
    assert json.loads(a["gen_ai.output.messages"]) == [
        {"role": "assistant", "parts": [{"type": "text", "content": "18 days [pto]"}], "finish_reason": "stop"}]
    assert "app.genai.cost_usd" not in a


def test_content_not_captured_by_default(s, spans, monkeypatch):
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False)
    _client(s).chat(get_models(s)["eis-gpt-mini"], "sys", "user q")
    a = spans.get_finished_spans()[0].attributes
    assert "gen_ai.input.messages" not in a and "gen_ai.output.messages" not in a


def test_emit_span_false_creates_no_span(s, spans):
    r = _client(s).chat(get_models(s)["eis-gpt-mini"], "sys", "u", emit_span=False)
    assert r.text and spans.get_finished_spans() == ()


def test_http_error_raises_without_body_and_marks_span(s, spans):
    with pytest.raises(EisError) as e:
        _client(s, body=b"secret prompt echo", status=403).chat(get_models(s)["eis-gpt-mini"], "s", "u")
    assert "403" in str(e.value) and "secret" not in str(e.value)
    sp = spans.get_finished_spans()[0]
    assert sp.attributes["error.type"] == "EisError" and not sp.status.is_ok


def test_error_event_in_stream_raises(s, spans):
    body = "﻿event: error\ndata: " + json.dumps({"error": {"message": "boom"}}) + "\n\n"
    with pytest.raises(EisError):
        _client(s, body=body.encode()).chat(get_models(s)["eis-gpt-mini"], "s", "u")


def test_missing_usage_is_zero(s, spans):
    body = sse(_chunks()[0], "[DONE]")
    r = _client(s, body=body).chat(get_models(s)["eis-gpt-mini"], "s", "u")
    assert (r.input_tokens, r.output_tokens) == (0, 0)


def test_rejects_non_eis_spec(s, spans):
    with pytest.raises(ValueError):
        _client(s).chat(get_models(s)["gemma"], "s", "u")


def test_client_timeout_matches_config(s):
    c = EisClient(s.model_copy(update={"llm_timeout_s": 42.0}))
    assert c._http.timeout.read == 42.0
