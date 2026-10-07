import httpx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.config import Settings
from app.llm_langchain import LangChainEngine
from app.llm_eis import EisCompletion
from app.llm_sdk import GemmaGate, GemmaOffline
from app.models import get_models
from app.personas import get_persona
from app.retrieval import Doc, RetrievalResult


@pytest.fixture
def s(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://e", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


def _gate(up=True):
    return GemmaGate("https://g/v1", "k", ttl_s=0.0, http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200 if up else 503, json={}))))


def _llm(text="ok [pto]"):
    msg = AIMessage(content=text, usage_metadata={"input_tokens": 90, "output_tokens": 12, "total_tokens": 102})
    return GenericFakeChatModel(messages=iter([msg]))


def _retrieve(result):
    return lambda q: result


def test_chain_returns_retrieval_prompt_and_usage(s):
    docs = [Doc("pto", "PTO", "public", "18 days", 1.0)]
    eng = LangChainEngine(s, _gate(), llm_factory=lambda spec: _llm())
    ret, built, res = eng.run(get_models(s)["eis-gemini-flash"], get_persona("employee"), "pto?",
                              _retrieve(RetrievalResult(docs, [], 5)))
    assert [d.id for d in ret.docs] == ["pto"] and built.doc_ids == ["pto"]
    assert (res.text, res.input_tokens, res.output_tokens, res.engine) == ("ok [pto]", 90, 12, "langchain")


def test_braces_in_documents_and_question_do_not_break_template(s):
    docs = [Doc("a", "A", "public", "{system} {0} \"x\" 😀", 1.0)]
    eng = LangChainEngine(s, _gate(), llm_factory=lambda spec: _llm())
    _, built, res = eng.run(get_models(s)["eis-gemini-flash"], get_persona("manager"), "{question}?",
                            _retrieve(RetrievalResult(docs, [], 1)))
    assert "{system} {0}" in built.user and res.text


def test_gemma_offline_raises_before_building_chain(s):
    eng = LangChainEngine(s, _gate(False), llm_factory=lambda spec: _llm())
    with pytest.raises(GemmaOffline):
        eng.run(get_models(s)["gemma"], get_persona("employee"), "q", _retrieve(RetrievalResult([], [], 0)))


def test_content_block_list_is_flattened_to_text(s):
    msg = AIMessage(content=[{"type": "text", "text": "18 days [pto]", "extras": {"signature": "zz"}}],
                    usage_metadata={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8})
    eng = LangChainEngine(s, _gate(), llm_factory=lambda spec: GenericFakeChatModel(messages=iter([msg])))
    _, _, res = eng.run(get_models(s)["eis-gemini-flash"], get_persona("employee"), "q",
                        _retrieve(RetrievalResult([Doc("pto", "PTO", "public", "18 days", 1.0)], [], 1)))
    assert res.text == "18 days [pto]"


def test_langchain_default_factory_uses_the_configured_timeout(monkeypatch, s):
    seen = {}
    monkeypatch.setattr("langchain_openai.ChatOpenAI", lambda **kw: seen.setdefault("openai", kw) or object())
    eng = LangChainEngine(s.model_copy(update={"llm_timeout_s": 42.0}), _gate())
    eng._default_factory(get_models(s)["gemma"])
    assert seen["openai"]["timeout"] == 42.0 and seen["openai"]["max_retries"] == 0


class FakeEis:
    def __init__(self):
        self._s = Settings(_env_file=None, obs_es_url="https://e", obs_es_admin_key="k", obs_kibana_url="https://k")
        self.calls = []

    def chat(self, spec, system, user, emit_span=True):
        self.calls.append((spec.key, system, user, emit_span))
        return EisCompletion("18 days [pto]", "openai-gpt-5.4-mini", 90, 12, "stop")


def test_eis_chat_model_runs_the_chain_without_a_second_span_and_reports_usage(s):
    eis = FakeEis()
    eng = LangChainEngine(s, _gate(), eis_client=eis)
    docs = [Doc("pto", "PTO", "public", "18 days", 1.0)]
    _, built, res = eng.run(get_models(s)["eis-gpt-mini"], get_persona("employee"), "pto?",
                            _retrieve(RetrievalResult(docs, [], 1)))
    assert (res.text, res.input_tokens, res.output_tokens, res.thinking_tokens, res.engine, res.model_id) == \
        ("18 days [pto]", 90, 12, 0, "langchain", "gpt-5.4-mini")
    key, system, user, emit_span = eis.calls[0]
    assert (key, system, user, emit_span) == ("eis-gpt-mini", built.system, built.user, False)


def test_eis_chat_model_ls_params_name_the_model_for_the_langchain_instrumentation(s):
    from app.llm_langchain import ChatElasticInference
    m = ChatElasticInference(client=FakeEis(), spec=get_models(s)["eis-claude-haiku"])
    p = m._get_ls_params()
    assert p["ls_provider"] == "elastic" and p["ls_model_name"] == "claude-4.5-haiku"
