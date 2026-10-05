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
