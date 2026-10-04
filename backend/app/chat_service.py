import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

from .cost import compute_cost
from .guardrail import GuardrailResult, aggregate_verdict
from .models import ModelSpec
from .personas import get_persona
from .pii import find_pii
from .prompt import NO_CONTEXT_ANSWER, build_prompt
from .retrieval import RetrievalResult
from .telemetry import emit_prompt_log, set_root_attrs, trace_id_hex

logger = logging.getLogger("app.chat_service")

# Inline blocking policy. The async pipeline flags every reason below (and the X-ray shows the
# FLAGGED verdict), but only a security-relevant subset stops the request. Ordinary HR questions
# that merely mention a salary or several colleagues are flagged-but-allowed; everything in
# BLOCKING_REASONS (prompt injection and direct identifiers) is blocked before retrieval or the LLM.
BLOCKING_REASONS = {"prompt_injection", "pii_email", "pii_nric", "pii_ssn", "pii_phone"}


@dataclass
class ChatRequest:
    message: str
    persona: str
    model: str
    engine: str


@dataclass
class Deps:
    retriever: object
    guardrail: object
    sdk: object
    langchain: object
    models: dict[str, ModelSpec]
    prices: dict | None = None
    emit_log: Callable = emit_prompt_log
    gate: object | None = None  # GemmaGate-like; consulted first so an offline VM answers 503 fast


@contextmanager
def _timed(stages: list, name: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        stages.append({"name": name, "ms": int((time.perf_counter() - t0) * 1000)})


def _docs(ret: RetrievalResult):
    return [{"id": d.id, "title": d.title, "classification": d.classification, "score": round(d.score, 4)}
            for d in ret.docs]


def _hidden(ret: RetrievalResult):
    return [{"id": g.id, "title": g.title, "classification": g.classification} for g in ret.hidden]


def run_chat(req: ChatRequest, deps: Deps) -> dict:
    persona = get_persona(req.persona)
    spec = deps.models[req.model]
    if spec.provider == "gemma" and deps.gate is not None:
        deps.gate.require()  # raises GemmaOffline before any guardrail / ES / LLM work
    stages: list[dict] = []
    set_root_attrs(app__persona=persona.id, app__genai__model=spec.model_id, app__genai__engine=req.engine)

    with _timed(stages, "guardrail.check"):
        try:
            g = deps.guardrail.check(req.message)
        except Exception:
            # Fail open on model faults; regex PII detection still applies.
            logger.warning("guardrail check failed; degrading", exc_info=True)
            g = GuardrailResult(aggregate_verdict("SAFE", 0.0, [], find_pii(req.message)), "degraded", 0)
    deps.emit_log(prompt=req.message, persona=persona.id, model=spec.model_id,
                  engine=req.engine, status=g.status)
    guard = {"verdict": g.verdict.verdict, "reasons": g.verdict.reasons, "status": g.status,
             "latency_ms": g.latency_ms, "injection_score": g.verdict.injection_score}
    set_root_attrs(app__guardrail__verdict=g.verdict.verdict, app__guardrail__status=g.status)

    base = {"trace_id": trace_id_hex(), "persona": persona.id, "model": spec.model_id,
            "engine": req.engine, "guardrail": guard, "stages": stages}

    if g.verdict.verdict == "FLAGGED" and set(g.verdict.reasons) & BLOCKING_REASONS:
        set_root_attrs(app__genai__cost_usd=0.0, app__blocked=True)
        return {**base, "answer": "", "blocked": True, "block_reason": g.verdict.reasons,
                "docs": [], "hidden": [],
                "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}, "cost_usd": 0.0}

    if req.engine == "langchain":
        with _timed(stages, "retrieval.hybrid"):
            ret = deps.retriever.search(persona.id, req.message)
        if not ret.docs:
            return _no_context(base, ret)
        with _timed(stages, "llm.generate"):  # prompt.build runs inside the chain
            *_, res = deps.langchain.run(spec, persona, req.message, lambda _q: ret)
    else:
        with _timed(stages, "retrieval.hybrid"):
            ret = deps.retriever.search(persona.id, req.message)
        with _timed(stages, "prompt.build"):
            built = build_prompt(persona, req.message, ret.docs)
        if built.no_context:
            return _no_context(base, ret)
        with _timed(stages, "llm.generate"):
            res = deps.sdk.generate(spec, built.system, built.user)

    cost = compute_cost(spec.model_id, res.input_tokens, res.output_tokens, res.thinking_tokens, deps.prices)
    # output_tokens is the billed total (visible output + thinking); thinking_tokens breaks the part out.
    set_root_attrs(app__genai__cost_usd=cost.total_usd, app__genai__input_tokens=res.input_tokens,
                   app__genai__output_tokens=res.output_tokens + res.thinking_tokens,
                   app__genai__thinking_tokens=res.thinking_tokens,
                   app__genai__cost_basis=cost.basis)
    return {**base, "answer": res.text, "blocked": False, "block_reason": [], "docs": _docs(ret),
            "hidden": _hidden(ret),
            "usage": {"input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                      "thinking_tokens": res.thinking_tokens},
            "cost_usd": cost.total_usd}


def _no_context(base: dict, ret: RetrievalResult) -> dict:
    set_root_attrs(app__genai__cost_usd=0.0)
    return {**base, "answer": NO_CONTEXT_ANSWER, "blocked": False, "block_reason": [], "docs": [],
            "hidden": _hidden(ret),
            "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}, "cost_usd": 0.0}
