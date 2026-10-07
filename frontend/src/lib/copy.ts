export const STAGE_LABELS: Record<string, string> = {
  "guardrail.check": "Guardrail check",
  "retrieval.hybrid": "Hybrid search",
  "prompt.build": "Prompt build",
  "llm.generate": "LLM call",
};

export const STAGE_HINTS: Record<string, string> = {
  "guardrail.check": "Prompt injection and entity models in Elasticsearch",
  "retrieval.hybrid": "ELSER + BM25, reranked, document level security applied",
  "prompt.build": "Persona, context and citations assembled",
  "llm.generate": "Model call with token usage",
};

export const REASON_LABELS: Record<string, string> = {
  prompt_injection: "Prompt injection attempt",
  pii_email: "Email address",
  pii_nric: "NRIC number",
  pii_ssn: "SSN",
  pii_phone: "Phone number",
  pii_salary: "Salary figure",
  pii_multiple_people: "Several named people",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code.replace(/_/g, " ");
}

export const CLASSIFICATION_LABEL: Record<string, string> = {
  public: "Public",
  internal: "Internal",
  confidential: "Confidential",
  restricted: "Restricted",
};

// Mirrors the interval of the glassbox-flagged-prompts rule in elastic/rules/guardrail_detection.py (checked by elastic/tests).
export const DETECTION_INTERVAL_MINUTES = 1;

export const DEVTOOLS_HELP = "Runs the same Elastic hosted models the app called, plus the ingest pipeline. Needs a Kibana login.";

export const QUALITY_HELP = "Runs the same Elastic hosted models, language detection and an LLM judge on this answer. Needs a Kibana login.";
export const QUALITY_TIMING = "Elastic scores each answer asynchronously, about 5 to 10 seconds after it is shown. The response log, dashboards and alerts fill in after that.";

export const OWASP_CHIPS: { id: string; name: string; detail: string }[] = [
  { id: "LLM02", name: "Sensitive information disclosure", detail: "PII and canary strings in the answer" },
  { id: "LLM05", name: "Improper output handling", detail: "Script tags or links the answer would hand to a browser" },
  { id: "LLM07", name: "System prompt leakage", detail: "Hidden instructions echoed back in the answer" },
  { id: "LLM09", name: "Misinformation (LLM judge)", detail: "Claims the cited documents do not support" },
];
export const QUALITY_CHIP = "Quality: sentiment, language, topic, answered";
