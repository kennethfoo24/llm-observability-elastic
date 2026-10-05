"""Offline stand-in for the real backend, used only for UI development and screenshots.

It reuses the real corpus and the real role rules (allowed_roles), the real PII regexes, the real
cost table and the real run_chat orchestration. Only Elasticsearch, the guardrail models and the LLMs
are faked, with deterministic keyword logic.
"""
import re
import time

from fastapi import FastAPI

from .chat_service import Deps
from .config import Settings
from .corpus_data import DOCS
from .guardrail import GuardrailResult, aggregate_verdict
from .llm_sdk import GemmaOffline, LLMResult
from .main import create_app
from .models import get_models
from .personas import get_persona
from .pii import find_pii
from .retrieval import Doc, Ghost, RetrievalResult

INJECTION_PATTERNS = ("ignore previous", "ignore all previous", "disregard", "system prompt", "reveal your instructions")
_WORD = re.compile(r"[a-z0-9]+")
_DOC_ID = re.compile(r'<document id="([^"]+)"')


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def _score(query: set[str], doc: dict) -> int:
    return len(query & _tokens(doc["title"] + " " + doc["content"]))


class StubRetriever:
    def __init__(self, delay: float):
        self.delay = delay

    def search(self, persona_id: str, text: str) -> RetrievalResult:
        time.sleep(0.12 * self.delay)
        role = get_persona(persona_id).role
        q = _tokens(text)
        scored = sorted(((d, _score(q, d)) for d in DOCS), key=lambda pair: -pair[1])
        scored = [(d, s) for d, s in scored if s > 0]
        visible = [(d, s) for d, s in scored if role in d["allowed_roles"]][:4]
        hidden = [d for d, _ in scored if role not in d["allowed_roles"]][:8]
        docs = [Doc(d["slug"], d["title"], d["classification"], d["content"], round(s * 1.7 + 0.3, 3)) for d, s in visible]
        return RetrievalResult(docs, [Ghost(d["slug"], d["title"], d["classification"]) for d in hidden], 118)


class StubGuardrail:
    def __init__(self, delay: float):
        self.delay = delay

    def check(self, text: str) -> GuardrailResult:
        time.sleep(0.04 * self.delay)
        injected = any(p in text.lower() for p in INJECTION_PATTERNS)
        verdict = aggregate_verdict("INJECTION" if injected else "SAFE", 0.99 if injected else 0.02, [], find_pii(text))
        verdict.injection_score = 0.99 if injected else 0.02
        return GuardrailResult(verdict, "ok", 41)


def _answer(user_text: str) -> str:
    ids = _DOC_ID.findall(user_text)
    if not ids:
        return "I could not find that in your documents."
    by_id = {d["slug"]: d for d in DOCS}
    first = by_id[ids[0]]["content"].split(". ")[0].rstrip(".") + "."
    extra = f" See also [{ids[1]}]." if len(ids) > 1 else ""
    return f"{first} [{ids[0]}]{extra}"


class StubSdk:
    def __init__(self, gate, delay: float):
        self.gate, self.delay = gate, delay

    def generate(self, spec, system: str, user: str) -> LLMResult:
        if spec.provider == "gemma":
            self.gate.require()
        time.sleep(0.45 * self.delay)
        text = _answer(user)
        thinking = 60 if spec.key == "eis-gemini-flash" else 0
        return LLMResult(text, spec.model_id, max(1, len(system + user) // 4), max(1, len(text) // 4), thinking, "sdk")


class StubLangChain:
    def __init__(self, sdk: StubSdk):
        self.sdk = sdk

    def run(self, spec, persona, question, retrieve):
        from .prompt import build_prompt
        ret = retrieve(question)
        built = build_prompt(persona, question, ret.docs)
        res = self.sdk.generate(spec, built.system, built.user)
        return ret, built, LLMResult(res.text, res.model_id, res.input_tokens, res.output_tokens, 0, "langchain")


class StubGate:
    def __init__(self, up: bool):
        self.up = up

    def is_up(self) -> bool:
        return self.up

    def require(self) -> None:
        if not self.up:
            raise GemmaOffline("Gemma VM is not serving; start kenneth-gemma-llm and wait for vLLM to load")


def build_stub_app(gemma_up: bool = True, latency_scale: float = 1.0, password: str = "demo") -> FastAPI:
    s = Settings(_env_file=None, obs_es_url="http://stub", obs_es_admin_key="stub",
                 obs_kibana_url="https://kibana.example", app_password=password)
    gate = StubGate(gemma_up)
    sdk = StubSdk(gate, latency_scale)
    deps = Deps(retriever=StubRetriever(latency_scale), guardrail=StubGuardrail(latency_scale), sdk=sdk,
                langchain=StubLangChain(sdk), models=get_models(s), emit_log=lambda **kw: None, gate=gate)
    return create_app(deps, s, gate=gate)
