export type Engine = "sdk" | "langchain";
export type Verdict = "CLEAN" | "FLAGGED" | "UNKNOWN";

export type Persona = { id: string; name: string; title: string; can_read_docs: number; total_docs: number };
export type ModelInfo = { key: string; label: string; provider: "eis" | "gemma"; model_id: string; available: boolean };
export type AppConfig = { kibana_url: string; security_kibana_url?: string | null; company: string;
  /** Elastic hosted model ids and ingest pipeline id the guardrail uses (single source: the backend). */
  guardrail_models?: { injection: string; ner: string }; guardrail_pipeline?: string;
  /** Ingest pipeline that scores each answer (OWASP and quality checks). */
  quality_pipeline?: string };

export type Guardrail = {
  verdict: Verdict;
  reasons: string[];
  status: "ok" | "degraded";
  latency_ms: number;
  /** null when the injection model did not answer (timeout, error, malformed): not scored, not zero */
  injection_score: number | null;
};
export type DocHit = { id: string; title: string; classification: string; score: number };
export type Ghost = { id: string; title: string; classification: string };
export type Usage = { input_tokens: number; output_tokens: number; thinking_tokens: number };
export type Stage = { name: string; ms: number };

export type ChatRequest = { message: string; persona: string; model: string; engine: Engine };
export type ChatResponse = {
  answer: string;
  blocked: boolean;
  block_reason: string[];
  trace_id: string;
  persona: string;
  model: string;
  engine: Engine;
  docs: DocHit[];
  hidden: Ghost[];
  usage: Usage;
  cost_usd: number;
  guardrail: Guardrail;
  stages: Stage[];
  /** Server-built context the response log carries (only documents the persona may see). */
  quality_context?: string;
};
