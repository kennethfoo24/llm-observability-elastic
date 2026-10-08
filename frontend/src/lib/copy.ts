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

export const CHECKS_TITLE = "What Elastic checks on this answer";

export type QualityCheck = { key: string; id: string; name: string; what: string; owaspUrl?: string; dashboard: "quality" | "owasp" };
const OWASP_BASE = "https://genai.owasp.org/llmrisk/";
export const QUALITY_CHECKS: QualityCheck[] = [
  { key: "llm02", id: "LLM02", name: "Sensitive information disclosure", dashboard: "owasp",
    what: "Looks for emails, phone numbers and other personal data in the answer (regex and entity model, genai-quality pipeline, step: PII scan).",
    owaspUrl: OWASP_BASE + "llm022025-sensitive-information-disclosure/" },
  { key: "llm05", id: "LLM05", name: "Improper output handling", dashboard: "owasp",
    what: "Flags script tags, event handlers and external links the answer would hand to a browser (genai-quality pipeline, step: markup check).",
    owaspUrl: OWASP_BASE + "llm052025-improper-output-handling/" },
  { key: "llm07", id: "LLM07", name: "System prompt leakage", dashboard: "owasp",
    what: "Checks whether the answer repeats the secret id hidden in the system prompt (genai-quality pipeline, step: canary check).",
    owaspUrl: OWASP_BASE + "llm072025-system-prompt-leakage/" },
  { key: "llm09", id: "LLM09", name: "Misinformation judged by an LLM", dashboard: "quality",
    what: "An LLM judge scores whether the cited documents support the answer (genai-quality pipeline, step: judge).",
    owaspUrl: OWASP_BASE + "llm092025-misinformation/" },
  { key: "sentiment", id: "Quality", name: "Sentiment", dashboard: "quality",
    what: "The judge reads the tone of the question as positive, neutral or negative (genai-quality pipeline, step: judge)." },
  { key: "language", id: "Quality", name: "Language", dashboard: "quality",
    what: "A language model compares the language of the question and the answer (genai-quality pipeline, step: language detection)." },
  { key: "topic", id: "Quality", name: "Topic", dashboard: "quality",
    what: "The judge decides whether the question is about workplace matters; a zero-shot model gives the topic label (genai-quality pipeline, steps: judge, topic)." },
  { key: "answered", id: "Quality", name: "Answered", dashboard: "quality",
    what: "Records whether the assistant actually answered or said it could not (app flag quality.answered, confirmed by the judge)." },
];
