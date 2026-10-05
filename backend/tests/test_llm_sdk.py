import time
from types import SimpleNamespace as NS

import httpx
import pytest

from app.config import Settings
from app.llm_eis import EisCompletion
from app.llm_sdk import GemmaGate, GemmaOffline, SdkEngine
from app.models import get_models


@pytest.fixture
def s(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://e", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


class FakeEis:
    def __init__(self, completion=None):
        self.last = None
        self.completion = completion or EisCompletion("18 days [pto-policy]", "openai-gpt-5.4-mini", 120, 30, "stop")

    def chat(self, spec, system, user, **kw):
        self.last = (spec, system, user, kw)
        return self.completion


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


def test_eis_result_maps_usage_and_uses_the_app_model_id(s):
    eis = FakeEis()
    r = SdkEngine(s, _gate(), eis_client=eis).generate(get_models(s)["eis-gpt-mini"], "sys", "user")
    assert (r.text, r.input_tokens, r.output_tokens, r.thinking_tokens, r.engine) == \
        ("18 days [pto-policy]", 120, 30, 0, "sdk")
    assert r.model_id == "gpt-5.4-mini"
    assert eis.last[1:3] == ("sys", "user") and eis.last[3] == {}  # the SDK path keeps the EIS chat span


def test_eis_models_do_not_consult_the_gemma_gate(s):
    r = SdkEngine(s, _gate(False), eis_client=FakeEis()).generate(get_models(s)["eis-claude-haiku"], "s", "u")
    assert r.text


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


@pytest.mark.parametrize("exc", [httpx.InvalidURL("bad url"), OSError("ssl: weird")])
def test_gate_treats_any_exception_as_offline(exc):
    def boom(request):
        raise exc
    gate = GemmaGate("https://gemma/v1", "k", ttl_s=0.0, http=httpx.Client(transport=httpx.MockTransport(boom)))
    assert gate.is_up() is False
    with pytest.raises(GemmaOffline):
        gate.require()


def test_sdk_clients_are_built_with_the_configured_timeout_and_no_hidden_retries(monkeypatch, s):
    seen = {}

    class FakeOpenAIClient:
        def __init__(self, **kw):
            seen["openai"] = kw

    monkeypatch.setattr("openai.OpenAI", FakeOpenAIClient)
    eng = SdkEngine(s.model_copy(update={"llm_timeout_s": 42.0}), GemmaGate("https://g/v1", "k"))
    eng._openai_client()
    assert seen["openai"]["timeout"] == 42.0 and seen["openai"]["max_retries"] == 0
