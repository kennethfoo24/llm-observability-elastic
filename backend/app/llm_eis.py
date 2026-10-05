"""Elastic Inference Service (EIS) chat completion client.

elasticsearch-py 9.5 has no unified chat completion method, so this streams
POST /_inference/chat_completion/<endpoint>/_stream over httpx and aggregates the SSE chunks.
No retries (a failed call surfaces as a 502, like the other LLM clients)."""
import json
import os
import time
from dataclasses import dataclass

import httpx
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from .config import Settings
from .models import ModelSpec

tracer = trace.get_tracer("glassbox.eis")
_CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
_CAPTURE_ON = {"span_only", "span_and_event", "true"}


class EisError(Exception):
    """Never carries the response body: it can echo request content."""


@dataclass
class EisCompletion:
    text: str
    response_model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


def _capture() -> bool:
    return os.environ.get(_CAPTURE_ENV, "").strip().lower() in _CAPTURE_ON


def _part(text: str) -> dict:
    return {"type": "text", "content": text}


class EisClient:
    def __init__(self, s: Settings, http: httpx.Client | None = None):
        self._s = s
        self._http = http or httpx.Client(timeout=httpx.Timeout(s.llm_timeout_s))

    def chat(self, spec: ModelSpec, system: str, user: str, *, emit_span: bool = True) -> EisCompletion:
        if spec.provider != "eis" or not spec.endpoint:
            raise ValueError(f"{spec.key} is not an EIS model")
        if not emit_span:  # LangChain's own instrumentation already emits the chat span
            return self._call(spec, system, user)
        with tracer.start_as_current_span(f"chat {spec.model_id}", kind=SpanKind.CLIENT) as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.provider.name", "elastic")
            span.set_attribute("gen_ai.request.model", spec.model_id)
            span.set_attribute("gen_ai.request.max_tokens", self._s.eis_max_tokens)
            capture = _capture()
            if capture:
                span.set_attribute("gen_ai.system_instructions", json.dumps([_part(system)]))
                span.set_attribute("gen_ai.input.messages", json.dumps(
                    [{"role": "user", "parts": [_part(user)]}]))
            try:
                r = self._call(spec, system, user)
            except Exception as e:
                span.set_attribute("error.type", type(e).__name__)
                span.set_status(Status(StatusCode.ERROR))
                raise
            if r.response_model:
                span.set_attribute("gen_ai.response.model", r.response_model)
            span.set_attribute("gen_ai.usage.input_tokens", r.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", r.output_tokens)
            if r.finish_reason:
                span.set_attribute("gen_ai.response.finish_reasons", [r.finish_reason])
            if capture:
                span.set_attribute("gen_ai.output.messages", json.dumps(
                    [{"role": "assistant", "parts": [_part(r.text)], "finish_reason": r.finish_reason or "stop"}]))
            return r

    def _call(self, spec: ModelSpec, system: str, user: str) -> EisCompletion:
        url = f"{self._s.obs_es_url.rstrip('/')}/_inference/chat_completion/{spec.endpoint}/_stream"
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_completion_tokens": self._s.eis_max_tokens}
        headers = {"Authorization": f"ApiKey {self._s.guardrail_es_key}", "Content-Type": "application/json"}
        deadline = time.monotonic() + self._s.llm_timeout_s
        parts: list[str] = []
        model, finish, tin, tout = "", "", 0, 0
        with self._http.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code != 200:
                raise EisError(f"EIS chat completion failed with HTTP {resp.status_code}")
            event = "message"
            for raw in resp.iter_lines():
                if time.monotonic() > deadline:
                    raise EisError("EIS chat completion exceeded the overall timeout")
                line = raw.lstrip("﻿").strip()
                if not line:
                    event = "message"
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                if event == "error":
                    raise EisError("EIS returned an error event")
                try:
                    chunk = json.loads(data)
                except ValueError:
                    raise EisError("EIS returned a malformed stream chunk") from None
                if "error" in chunk:
                    raise EisError("EIS returned an error event")
                model = chunk.get("model") or model
                for ch in chunk.get("choices") or []:
                    parts.append((ch.get("delta") or {}).get("content") or "")
                    finish = ch.get("finish_reason") or finish
                u = chunk.get("usage")
                if u:
                    tin, tout = u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0
        return EisCompletion("".join(parts), model, tin, tout, finish)
