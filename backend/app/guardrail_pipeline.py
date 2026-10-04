from .pii import PII_PATTERNS

PIPELINE_ID = "genai-guardrail"
INJECTION_MODEL = "protectai__deberta-v3-base-prompt-injection-v2"
NER_MODEL = "elastic__distilbert-base-cased-finetuned-conll03-english"
PROMPT_FIELD = "attributes.genai.prompt_text"   # confirmed by Phase 0
GUARD_PREFIX = "attributes.security"            # Phase 0: top-level security.* is not indexed in logs data streams
HOOK_CONDITION = "ctx.data_stream?.dataset == 'genai_guardrail.otel' || ctx.data_stream?.dataset == 'genai_guardrail'"

VERDICT_SCRIPT = """
Map g = ctx.guard_tmp;
if (g == null) { g = new HashMap(); ctx.guard_tmp = g; }
List reasons = new ArrayList();
double injScore = 0.0;   // probability of the predicted label (drives the threshold test)
double pInj = 0.0;       // P(injection): what gets stored; 0.0 when there is no prediction
String injLabel = 'UNKNOWN';
if (g.containsKey('injection') && g.injection != null) {
  injLabel = g.injection.predicted_value;
  injScore = g.injection.prediction_probability;
  pInj = injLabel == 'INJECTION' ? injScore : 1.0 - injScore;
}
if (injLabel == 'INJECTION' && injScore >= params.injection_threshold) { reasons.add('prompt_injection'); }
if (g.containsKey('rx') && g.rx != null) {
  for (def k : g.rx.keySet()) { reasons.add('pii_' + k); }
}
Set people = new HashSet();
if (g.containsKey('ner') && g.ner != null && g.ner.entities != null) {
  for (def e : g.ner.entities) {
    if (e.class_name == 'PER' && e.class_probability >= params.ner_threshold) { people.add(e.entity); }
  }
}
if (people.size() >= 2) { reasons.add('pii_multiple_people'); }
boolean modelsOk = g.containsKey('injection') && g.injection != null && g.containsKey('ner') && g.ner != null;
g.models_ok = modelsOk;
g.threat_verdict = !reasons.isEmpty() ? 'FLAGGED' : (modelsOk ? 'CLEAN' : 'UNKNOWN');
g.threat_reasons = reasons;
g.injection_score = pInj;  // P(injection), not the confidence of the predicted class
g.person_count = people.size();
g.remove('ner');
g.remove('rx');
g.remove('injection');
"""


def _grok_processors() -> list[dict]:
    return [{
        "grok": {
            "field": PROMPT_FIELD,
            "patterns": [f"%{{GENAI_{name.upper()}:guard_tmp.rx.{name}}}"],
            "pattern_definitions": {f"GENAI_{name.upper()}": rx},
            "ignore_missing": True,
            "ignore_failure": True,
        }
    } for name, rx in PII_PATTERNS.items()]


def build_pipeline(include_inference: bool = True) -> dict:
    # OTLP log attributes arrive as flat dotted keys (attributes["genai.prompt_text"]); grok/script
    # need the nested path, so expand first (no-op when the field is already nested or absent).
    processors: list[dict] = [{"dot_expander": {
        "field": PROMPT_FIELD.split(".", 1)[1], "path": PROMPT_FIELD.split(".", 1)[0],
        "ignore_failure": True}}]
    if include_inference:
        processors += [
            {"inference": {"model_id": INJECTION_MODEL, "target_field": "guard_tmp.injection",
                           "field_map": {PROMPT_FIELD: "text_field"}, "ignore_failure": True}},
            {"inference": {"model_id": NER_MODEL, "target_field": "guard_tmp.ner",
                           "field_map": {PROMPT_FIELD: "text_field"}, "ignore_failure": True}},
        ]
    processors += _grok_processors()
    processors += [
        {"script": {"lang": "painless", "source": VERDICT_SCRIPT,
                    "params": {"injection_threshold": 0.85, "ner_threshold": 0.8}}},
        {"rename": {"field": "guard_tmp", "target_field": GUARD_PREFIX}},
    ]
    return {
        "description": "Prompt-injection + PII guardrail verdict for GenAI prompt logs",
        "processors": processors,
        "on_failure": [{"set": {"field": f"{GUARD_PREFIX}.threat_verdict", "value": "UNKNOWN"}},
                       {"remove": {"field": "guard_tmp", "ignore_missing": True, "ignore_failure": True}}],
    }


def build_hook(existing: dict | None) -> dict:
    hook = {"pipeline": {"name": PIPELINE_ID, "if": HOOK_CONDITION, "ignore_failure": True}}
    processors = list((existing or {}).get("processors", []))
    if not any(p.get("pipeline", {}).get("name") == PIPELINE_ID for p in processors):
        processors.append(hook)
    return {**(existing or {}), "processors": processors}
