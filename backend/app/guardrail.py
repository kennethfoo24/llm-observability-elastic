import contextvars
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace

from opentelemetry import trace

from .pii import find_pii

tracer = trace.get_tracer("glassbox.guardrail")
logger = logging.getLogger(__name__)
POOL_WORKERS = 16
PROMPT_ATTR_MAX_CHARS = 4096
_CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
_CAPTURE_ON = {"span_only", "span_and_event", "true"}


def capture_content_enabled() -> bool:
    """Same switch as the gen_ai content capture; default off."""
    return os.environ.get(_CAPTURE_ENV, "").strip().lower() in _CAPTURE_ON


@dataclass
class Verdict:
    """injection_score is P(injection) in [0, 1]: ~0 for confident SAFE predictions, ~1 for confident
    INJECTION ones, and None when the injection model gave no usable prediction (timeout, error or
    malformed). None means "not scored"; it must never be shown as a clean 0."""
    verdict: str
    reasons: list[str] = field(default_factory=list)
    injection_score: float | None = 0.0
    person_count: int = 0


@dataclass
class GuardrailResult:
    verdict: Verdict
    status: str
    latency_ms: int


def injection_probability(label: str, label_probability: float) -> float:
    """The model reports the probability of its *predicted* class; convert to P(injection)."""
    return label_probability if label == "INJECTION" else 1.0 - label_probability


def aggregate_verdict(injection_label: str, injection_score: float, entities: list[dict],
                      pii_hits: list[str], injection_threshold: float = 0.85,
                      ner_threshold: float = 0.8) -> Verdict:
    # injection_score here is the probability of injection_label (what the model returns), which is
    # what the threshold test needs; the returned Verdict carries it as-is. Guardrail.check overrides
    # Verdict.injection_score with P(injection).
    reasons: list[str] = []
    if injection_label == "INJECTION" and injection_score >= injection_threshold:
        reasons.append("prompt_injection")
    reasons += [f"pii_{name}" for name in pii_hits]
    people = {e["entity"] for e in entities
              if e.get("class_name") == "PER" and e.get("class_probability", 0) >= ner_threshold}
    if len(people) >= 2:
        reasons.append("pii_multiple_people")
    return Verdict("FLAGGED" if reasons else "CLEAN", reasons, injection_score, len(people))


class Guardrail:
    def __init__(self, es, injection_model: str, ner_model: str, timeout_s: float):
        self._es, self._inj, self._ner, self._timeout = es, injection_model, ner_model, timeout_s
        self._pool = ThreadPoolExecutor(max_workers=POOL_WORKERS)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _infer(self, model_id: str, text: str) -> dict:
        r = self._es.options(request_timeout=self._timeout).ml.infer_trained_model(
            model_id=model_id, docs=[{"text_field": text}])
        return r["inference_results"][0]

    def _submit(self, model_id: str, text: str):
        ctx = contextvars.copy_context()
        return self._pool.submit(ctx.run, self._infer, model_id, text)

    def check(self, text: str) -> GuardrailResult:
        start = time.perf_counter()
        with tracer.start_as_current_span("guardrail.check") as span:
            if capture_content_enabled():
                span.set_attribute("guardrail.prompt_text", text[:PROMPT_ATTR_MAX_CHARS])
            pii = find_pii(text)
            label, score, entities = "SAFE", 0.0, []
            p_inj: float | None = None
            futures = {"injection": self._submit(self._inj, text),
                       "ner": self._submit(self._ner, text)}
            done, _ = wait(list(futures.values()), timeout=self._timeout)
            degraded: list[str] = []
            for name, f in futures.items():
                if f not in done:
                    f.cancel()
                    degraded.append(f"{name}:timeout")
                    continue
                exc = f.exception()
                if exc is not None:
                    logger.warning("guardrail model call failed", exc_info=exc)
                    span.record_exception(exc)
                    degraded.append(f"{name}:{type(exc).__name__}")
                    continue
                res = f.result()
                if name == "injection":
                    try:
                        label = res["predicted_value"]
                        score = float(res["prediction_probability"])
                    except (KeyError, TypeError, ValueError):
                        label, score = "SAFE", 0.0
                        degraded.append("injection:malformed")
                    else:
                        p_inj = injection_probability(label, score)
                else:
                    entities = res.get("entities", [])
            status = "degraded" if degraded else "ok"
            verdict = replace(aggregate_verdict(label, score, entities, pii), injection_score=p_inj)
            ms = int((time.perf_counter() - start) * 1000)
            span.set_attribute("guardrail.status", status)
            span.set_attribute("guardrail.verdict", verdict.verdict)
            if verdict.injection_score is not None:
                span.set_attribute("guardrail.injection_score", verdict.injection_score)
            span.set_attribute("guardrail.reasons", ",".join(verdict.reasons))
            span.set_attribute("guardrail.person_count", verdict.person_count)
            span.set_attribute("guardrail.latency_ms", ms)
            if degraded:
                span.set_attribute("guardrail.degraded_reason", ",".join(degraded))
            return GuardrailResult(verdict, status, ms)
