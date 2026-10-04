import httpx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.config import Settings
from app.llm_langchain import LangChainEngine
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
    ret, built, res = eng.run(get_models(s)["flash-lite"], get_persona("employee"), "pto?",
                              _retrieve(RetrievalResult(docs, [], 5)))
    assert [d.id for d in ret.docs] == ["pto"] and built.doc_ids == ["pto"]
    assert (res.text, res.input_tokens, res.output_tokens, res.engine) == ("ok [pto]", 90, 12, "langchain")


def test_braces_in_documents_and_question_do_not_break_template(s):
    docs = [Doc("a", "A", "public", "{system} {0} \"x\" 😀", 1.0)]
    eng = LangChainEngine(s, _gate(), llm_factory=lambda spec: _llm())
    _, built, res = eng.run(get_models(s)["flash-lite"], get_persona("hr"), "{question}?",
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
    _, _, res = eng.run(get_models(s)["flash-lite"], get_persona("employee"), "q",
                        _retrieve(RetrievalResult([Doc("pto", "PTO", "public", "18 days", 1.0)], [], 1)))
    assert res.text == "18 days [pto]"
