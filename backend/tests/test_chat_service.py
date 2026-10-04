import pytest

from app.chat_service import ChatRequest, Deps, run_chat
from app.guardrail import GuardrailResult, Verdict
from app.llm_sdk import GemmaOffline, LLMResult
from app.models import ModelSpec
from app.prompt import NO_CONTEXT_ANSWER
from app.retrieval import Doc, Ghost, RetrievalResult

PRICES = {"models": {"gemini-3.1-flash-lite": {"input_per_mtok": 0.25, "output_per_mtok": 1.5}}}
SPEC = ModelSpec("flash-lite", "Flash-Lite", "vertex", "gemini-3.1-flash-lite")
GEMMA = ModelSpec("gemma", "Gemma", "gemma", "google/gemma-4-31B-it")
CONTRACT_KEYS = {"answer", "blocked", "block_reason", "trace_id", "persona", "model", "engine", "docs",
                 "hidden", "usage", "cost_usd", "guardrail", "stages"}


class LogSink:
    def __init__(self): self.calls = []
    def __call__(self, **kw): self.calls.append(kw)


class FakeRetriever:
    def __init__(self, result): self.result, self.calls = result, 0

    def search(self, persona_id, text):
        self.calls += 1
        return self.result


class FakeGuardrail:
    def __init__(self, verdict="CLEAN", status="ok", reasons=()):
        self.v = GuardrailResult(Verdict(verdict, list(reasons), 0.1, 0), status, 12)

    def check(self, text): return self.v


class RaisingGuardrail:
    def check(self, text): raise KeyError("malformed model payload")


class FakeSdk:
    def __init__(self, boom=None): self.calls, self.boom = 0, boom

    def generate(self, spec, system, user):
        self.calls += 1
        if self.boom: raise self.boom
        return LLMResult("18 days [pto]", spec.model_id, 3000, 400, 0, "sdk")


class FakeLc:
    def run(self, spec, persona, question, retrieve):
        ret = retrieve(question)
        from app.prompt import build_prompt
        return ret, build_prompt(persona, question, ret.docs), LLMResult("lc answer", spec.model_id, 100, 10, 0, "langchain")


class Gate:
    def __init__(self, up): self.up = up

    def require(self):
        if not self.up:
            raise GemmaOffline("off")


def _deps(result=None, guard=None, sdk=None, gate=None):
    docs = [Doc("pto", "PTO", "public", "18 days", 2.0)]
    d = Deps(retriever=FakeRetriever(result or RetrievalResult(docs, [Ghost("aurora", "Aurora", "restricted")], 5)),
             guardrail=guard or FakeGuardrail(), sdk=sdk or FakeSdk(), langchain=FakeLc(),
             models={"flash-lite": SPEC, "gemma": GEMMA}, prices=PRICES, emit_log=LogSink(), gate=gate)
    return d


REQ = ChatRequest("how many pto days?", "employee", "flash-lite", "sdk")


def test_happy_path_returns_xray_payload_and_cost():
    out = run_chat(REQ, _deps())
    assert out["answer"] == "18 days [pto]" and not out["blocked"]
    assert out["usage"] == {"input_tokens": 3000, "output_tokens": 400, "thinking_tokens": 0}
    assert out["cost_usd"] == pytest.approx(0.00135)
    assert [s["name"] for s in out["stages"]] == ["guardrail.check", "retrieval.hybrid", "prompt.build", "llm.generate"]
    assert out["hidden"][0]["id"] == "aurora" and out["docs"][0]["id"] == "pto"
    assert out["guardrail"]["verdict"] == "CLEAN"


def test_prompt_log_emitted_for_every_request_including_blocked():
    d = _deps(guard=FakeGuardrail("FLAGGED", reasons=["prompt_injection"]))
    run_chat(REQ, d)
    assert len(d.emit_log.calls) == 1 and d.emit_log.calls[0]["prompt"] == REQ.message and d.emit_log.calls[0]["persona"] == "employee"


def test_flagged_prompt_is_blocked_before_retrieval_or_llm():
    d = _deps(guard=FakeGuardrail("FLAGGED", reasons=["prompt_injection"]))
    out = run_chat(REQ, d)
    assert out["blocked"] and out["block_reason"] == ["prompt_injection"] and out["cost_usd"] == 0
    assert d.retriever.calls == 0 and d.sdk.calls == 0


def test_degraded_guardrail_fails_open_and_request_succeeds():
    out = run_chat(REQ, _deps(guard=FakeGuardrail("CLEAN", status="degraded")))
    assert not out["blocked"] and out["guardrail"]["status"] == "degraded" and out["answer"]


def test_no_visible_docs_returns_canned_answer_without_llm_or_cost():
    d = _deps(result=RetrievalResult([], [Ghost("aurora", "Aurora", "restricted")], 5))
    out = run_chat(REQ, d)
    assert out["answer"] == NO_CONTEXT_ANSWER and out["cost_usd"] == 0 and d.sdk.calls == 0
    assert out["hidden"][0]["id"] == "aurora"


def test_gemma_offline_propagates_for_the_api_layer():
    with pytest.raises(GemmaOffline):
        run_chat(ChatRequest("q", "employee", "flash-lite", "sdk"), _deps(sdk=FakeSdk(boom=GemmaOffline("off"))))


def test_langchain_engine_path_reports_engine_and_cost_once():
    out = run_chat(ChatRequest("pto?", "employee", "flash-lite", "langchain"), _deps())
    assert out["engine"] == "langchain" and out["answer"] == "lc answer"
    assert out["cost_usd"] == pytest.approx(100 * 0.25 / 1e6 + 10 * 1.5 / 1e6)


def test_langchain_no_docs_skips_chain_and_cost():
    d = _deps(result=RetrievalResult([], [], 1))
    out = run_chat(ChatRequest("reorg?", "employee", "flash-lite", "langchain"), d)
    assert out["answer"] == NO_CONTEXT_ANSWER and out["cost_usd"] == 0


def test_guardrail_exception_fails_open_for_benign_prompt(caplog):
    d = _deps(guard=RaisingGuardrail())
    with caplog.at_level("WARNING", logger="app.chat_service"):
        out = run_chat(REQ, d)
    assert not out["blocked"] and out["answer"] == "18 days [pto]"
    assert out["guardrail"]["status"] == "degraded" and out["guardrail"]["verdict"] == "CLEAN"
    assert len(d.emit_log.calls) == 1 and d.emit_log.calls[0]["status"] == "degraded"
    assert any(r.name == "app.chat_service" and r.exc_info for r in caplog.records)


def test_guardrail_exception_still_blocks_regex_pii():
    d = _deps(guard=RaisingGuardrail())
    out = run_chat(ChatRequest("email alex.tan@nimbus-corp.example the file", "employee", "flash-lite", "sdk"), d)
    assert out["blocked"] and out["block_reason"] == ["pii_email"]
    assert out["guardrail"]["status"] == "degraded"
    assert d.retriever.calls == 0 and d.sdk.calls == 0
    assert len(d.emit_log.calls) == 1


@pytest.mark.parametrize("engine,kind", [("sdk", "happy"), ("sdk", "blocked"), ("sdk", "nocontext"),
                                         ("langchain", "happy"), ("langchain", "nocontext")])
def test_response_has_exact_contract_keys(engine, kind):
    if kind == "blocked":
        d = _deps(guard=FakeGuardrail("FLAGGED", reasons=["prompt_injection"]))
    elif kind == "nocontext":
        d = _deps(result=RetrievalResult([], [Ghost("aurora", "Aurora", "restricted")], 5))
    else:
        d = _deps()
    out = run_chat(ChatRequest("pto?", "employee", "flash-lite", engine), d)
    assert set(out) == CONTRACT_KEYS
    assert set(out["usage"]) == {"input_tokens", "output_tokens", "thinking_tokens"}
    assert set(out["guardrail"]) == {"verdict", "reasons", "status", "latency_ms", "injection_score"}


@pytest.mark.parametrize("engine", ["sdk", "langchain"])
def test_gemma_offline_fails_fast_before_any_guardrail_or_retrieval_work(engine):
    class CountingGuard(FakeGuardrail):
        calls = 0
        def check(self, text):
            CountingGuard.calls += 1
            return super().check(text)

    d = _deps(guard=CountingGuard(), gate=Gate(up=False))
    with pytest.raises(GemmaOffline):
        run_chat(ChatRequest("pto?", "employee", "gemma", engine), d)
    assert CountingGuard.calls == 0 and d.retriever.calls == 0 and d.sdk.calls == 0
    assert d.emit_log.calls == []


def test_gate_not_consulted_for_vertex_models():
    class Boom:
        def require(self): raise AssertionError("gate must not be called")
    out = run_chat(REQ, _deps(gate=Boom()))
    assert not out["blocked"]


@pytest.mark.parametrize("reasons", [["pii_salary"], ["pii_multiple_people"], ["pii_salary", "pii_multiple_people"]])
def test_non_security_flags_are_logged_but_do_not_block(reasons):
    d = _deps(guard=FakeGuardrail("FLAGGED", reasons=reasons))
    out = run_chat(REQ, d)
    assert not out["blocked"] and out["block_reason"] == [] and out["answer"] == "18 days [pto]"
    assert out["guardrail"]["verdict"] == "FLAGGED" and out["guardrail"]["reasons"] == reasons
    assert d.retriever.calls == 1 and d.sdk.calls == 1 and len(d.emit_log.calls) == 1


@pytest.mark.parametrize("reason", ["prompt_injection", "pii_email", "pii_nric", "pii_ssn", "pii_phone"])
def test_security_reasons_block(reason):
    d = _deps(guard=FakeGuardrail("FLAGGED", reasons=[reason]))
    out = run_chat(REQ, d)
    assert out["blocked"] and out["block_reason"] == [reason] and d.retriever.calls == 0 and d.sdk.calls == 0


def test_mixed_salary_and_email_blocks_with_all_reasons_listed():
    d = _deps(guard=FakeGuardrail("FLAGGED", reasons=["pii_salary", "pii_email"]))
    out = run_chat(REQ, d)
    assert out["blocked"] and out["block_reason"] == ["pii_salary", "pii_email"]
    assert d.retriever.calls == 0
