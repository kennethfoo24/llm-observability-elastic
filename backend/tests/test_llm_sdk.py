import time
from types import SimpleNamespace as NS

import httpx
import pytest

from app.config import Settings
from app.llm_sdk import GemmaGate, GemmaOffline, SdkEngine
from app.models import get_models


@pytest.fixture
def s(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://e", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


class FakeGenai:
    def __init__(self):
        self.models = self
        self.last = None

    def generate_content(self, model, contents, config):
        self.last = (model, contents, config)
        usage = NS(prompt_token_count=120, candidates_token_count=30, thoughts_token_count=50)
        return NS(text="18 days [pto-policy]", usage_metadata=usage)


class FakeOpenAI:
    def __init__(self):
        self.chat = NS(completions=self)

    def create(self, model, messages):
        msg = NS(content="answer from gemma")
        return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=200, completion_tokens=40))


def _gate(up=True):
    def handler(request):
        return httpx.Response(200 if up else 503, json={"data": []})
    return GemmaGate("https://gemma/v1", "k", ttl_s=0.0, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_gemini_result_includes_thinking_tokens(s):
    eng = SdkEngine(s, _gate(), genai_client=FakeGenai())
    r = eng.generate(get_models(s)["flash-lite"], "sys", "user")
    assert (r.text, r.input_tokens, r.output_tokens, r.thinking_tokens, r.engine) == \
        ("18 days [pto-policy]", 120, 30, 50, "sdk")
    assert r.model_id == s.gemini_flash_lite_id


def test_gemma_via_openai_client(s):
    eng = SdkEngine(s, _gate(True), openai_client=FakeOpenAI())
    r = eng.generate(get_models(s)["gemma"], "sys", "user")
    assert r.model_id == "google/gemma-4-31B-it" and r.input_tokens == 200 and r.output_tokens == 40


def test_gemma_offline_raises_quickly_without_calling_llm(s):
    eng = SdkEngine(s, _gate(False), openai_client=FakeOpenAI())
    t0 = time.perf_counter()
    with pytest.raises(GemmaOffline):
        eng.generate(get_models(s)["gemma"], "sys", "user")
    assert time.perf_counter() - t0 < 3


def test_gate_treats_connection_error_as_offline():
    def boom(request):
        raise httpx.ConnectError("refused")
    gate = GemmaGate("https://gemma/v1", "k", ttl_s=0.0, http=httpx.Client(transport=httpx.MockTransport(boom)))
    assert gate.is_up() is False


def test_gate_caches_result_for_ttl():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={})
    gate = GemmaGate("https://g/v1", "k", ttl_s=60.0, http=httpx.Client(transport=httpx.MockTransport(handler)))
    gate.is_up(); gate.is_up()
    assert len(calls) == 1


def test_gemma_tolerates_missing_usage_and_empty_choices(s):
    class NoUsage(FakeOpenAI):
        def create(self, model, messages):
            return NS(choices=[NS(message=NS(content="hi"))], usage=None)

    class NoChoices(FakeOpenAI):
        def create(self, model, messages):
            return NS(choices=[], usage=NS(prompt_tokens=7, completion_tokens=0))

    spec = get_models(s)["gemma"]
    r = SdkEngine(s, _gate(True), openai_client=NoUsage()).generate(spec, "sys", "user")
    assert (r.text, r.input_tokens, r.output_tokens) == ("hi", 0, 0)
    r = SdkEngine(s, _gate(True), openai_client=NoChoices()).generate(spec, "sys", "user")
    assert (r.text, r.input_tokens, r.output_tokens) == ("", 7, 0)


def test_gemini_tolerates_missing_usage_metadata(s):
    class NoUsage(FakeGenai):
        def generate_content(self, model, contents, config):
            return NS(text=None, usage_metadata=None)

    r = SdkEngine(s, _gate(), genai_client=NoUsage()).generate(get_models(s)["flash-lite"], "sys", "user")
    assert (r.text, r.input_tokens, r.output_tokens, r.thinking_tokens) == ("", 0, 0, 0)
