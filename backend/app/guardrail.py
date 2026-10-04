import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field

from opentelemetry import trace

from .pii import find_pii

tracer = trace.get_tracer("glassbox.guardrail")


@dataclass
class Verdict:
    verdict: str
    reasons: list[str] = field(default_factory=list)
    injection_score: float = 0.0
    person_count: int = 0


@dataclass
class GuardrailResult:
    verdict: Verdict
    status: str
    latency_ms: int


def aggregate_verdict(injection_label: str, injection_score: float, entities: list[dict],
                      pii_hits: list[str], injection_threshold: float = 0.85,
                      ner_threshold: float = 0.8) -> Verdict:
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
        self._pool = ThreadPoolExecutor(max_workers=4)

    def _infer(self, model_id: str, text: str) -> dict:
        r = self._es.ml.infer_trained_model(model_id=model_id, docs=[{"text_field": text}])
        return r["inference_results"][0]

    def check(self, text: str) -> GuardrailResult:
        start = time.perf_counter()
        with tracer.start_as_current_span("guardrail.check") as span:
            pii = find_pii(text)
            label, score, entities, status = "SAFE", 0.0, [], "ok"
            futures = [self._pool.submit(self._infer, self._inj, text),
                       self._pool.submit(self._infer, self._ner, text)]
            try:
                inj = futures[0].result(timeout=self._timeout)
                ner = futures[1].result(timeout=self._timeout)
                label = inj.get("predicted_value", "SAFE")
                score = float(inj.get("prediction_probability", 0.0))
                entities = ner.get("entities", [])
            except (FutureTimeout, Exception):  # noqa: BLE001 - fail open by design
                status = "degraded"
                for f in futures:
                    f.cancel()
            verdict = aggregate_verdict(label, score, entities, pii)
            ms = int((time.perf_counter() - start) * 1000)
            span.set_attribute("guardrail.status", status)
            span.set_attribute("guardrail.verdict", verdict.verdict)
            span.set_attribute("guardrail.injection_score", verdict.injection_score)
            span.set_attribute("guardrail.reasons", ",".join(verdict.reasons))
            return GuardrailResult(verdict, status, ms)
