import { compressToEncodedURIComponent } from "lz-string";
// Pure Kibana deep-link builders. Base URLs come from /api/config, never from source.
// Kibana keeps app state in the URL as rison (the same format its Share menu produces).

export const DETECTION_RULE_ID = "glassbox-flagged-prompts";
export const DASHBOARD_ID = "glassbox-overview";

/** Rison string: single quoted, with ! escaping ' and !. */
export function rison(s: string): string {
  return `'${s.replace(/!/g, "!!").replace(/'/g, "!'")}'`;
}

export function traceUrl(base: string, traceId: string): string {
  return `${base}/app/apm/link-to/trace/${encodeURIComponent(traceId)}`;
}

/** Security alerts page filtered to the LLM Observability detection rule, last 24 hours. */
export function alertsUrl(base: string): string {
  const query = `(language:kuery,query:${rison(`kibana.alert.rule.rule_id : "${DETECTION_RULE_ID}"`)})`;
  const timerange = `(global:(linkTo:!(),timerange:(from:now-24h,kind:relative,to:now)))`;
  return `${base}/app/security/alerts?query=${encodeURIComponent(query)}&timerange=${encodeURIComponent(timerange)}`;
}

/** Discover in ES|QL mode showing one hr-kb document (the retriever's hit id is the Elasticsearch _id). */
export function docDiscoverUrl(base: string, docId: string): string {
  const quoted = `"${docId.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  const esql = `FROM hr-kb METADATA _id | WHERE _id == ${quoted}`;
  const a = `(dataSource:(type:esql),query:(esql:${rison(esql)}))`;
  return `${base}/app/discover#/?_a=${encodeURIComponent(a)}`;
}

export function costDashboardUrl(base: string): string {
  return `${base}/app/dashboards#/view/${DASHBOARD_ID}`;
}

export type GuardrailConfig = { models: { injection: string; ner: string }; pipeline: string };

/** Longest Dev Tools share URL we will build; longer prompts are truncated in the payload. */
export const MAX_DEVTOOLS_URL_CHARS = 8000;
const CONSOLE_PREFIX = "/app/dev_tools#/console?load_from=data:text/plain,";

const body = (v: unknown) => JSON.stringify(v, null, 2);

/** The three Console requests for one prompt. JSON.stringify does all escaping. */
export function devToolsConsoleText(prompt: string, g: GuardrailConfig, note?: string): string {
  const docs = { docs: [{ text_field: prompt }] };
  const simulate = { docs: [{ _source: { attributes: { "genai.prompt_text": prompt }, data_stream: { dataset: "genai_guardrail" } } }] };
  return [
    ...(note ? [`# ${note}`, ""] : []),
    "# Prompt-injection model (DeBERTa), hosted on Elastic",
    `POST _ml/trained_models/${g.models.injection}/_infer`,
    body(docs),
    "",
    "# Named-entity model (DistilBERT NER), hosted on Elastic",
    `POST _ml/trained_models/${g.models.ner}/_infer`,
    body(docs),
    "",
    "# The full guardrail ingest pipeline: models + PII patterns + verdict script",
    `POST _ingest/pipeline/${g.pipeline}/_simulate`,
    body(simulate),
    "",
  ].join("\n");
}

/** Kibana Dev Tools Console deep link (the "Open in Console" share format: LZ-compressed text in load_from). */
export function devToolsUrl(base: string, prompt: string, g: GuardrailConfig): string {
  const build = (p: string, note?: string) => `${base}${CONSOLE_PREFIX}${compressToEncodedURIComponent(devToolsConsoleText(p, g, note))}`;
  let url = build(prompt);
  if (url.length <= MAX_DEVTOOLS_URL_CHARS) return url;
  let keep = prompt.length;
  while (keep > 0) {
    keep = Math.floor(keep * 0.8);
    const cut = Array.from(prompt.slice(0, keep)).join("");
    url = build(cut, `Prompt truncated to ${cut.length} characters to fit the link. Paste the full prompt to try it in full.`);
    if (url.length <= MAX_DEVTOOLS_URL_CHARS) break;
  }
  return url;
}

export const QUALITY_DASHBOARD_ID = "glassbox-quality";
export const OWASP_DASHBOARD_ID = "glassbox-owasp";

export function qualityDashboardUrl(base: string): string {
  return `${base}/app/dashboards#/view/${QUALITY_DASHBOARD_ID}`;
}

export function owaspDashboardUrl(base: string): string {
  return `${base}/app/dashboards#/view/${OWASP_DASHBOARD_ID}`;
}

/** Discover (ES|QL) on the Observability project: the genai_response log written for one trace. */
export function responseLogUrl(base: string, traceId: string): string {
  const quoted = `"${traceId.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  const esql = `FROM logs-genai_response* | WHERE trace_id == ${quoted}`;
  const a = `(dataSource:(type:esql),query:(esql:${rison(esql)}))`;
  return `${base}/app/discover#/?_a=${encodeURIComponent(a)}`;
}

/** The flat attributes the app logs for one answered response (the genai_response log). */
export type QualityInput = {
  prompt: string; response: string; context: string;
  citedIds: string[]; retrievedIds: string[]; topScore: number; hiddenCount: number;
  answered: boolean; persona: string;
};

export function qualityConsoleText(q: QualityInput, pipeline: string, note?: string): string {
  const doc = {
    docs: [{ _source: {
      attributes: {
        "genai.prompt_text": q.prompt, "genai.response_text": q.response, "genai.context_text": q.context,
        "genai.cited_ids": q.citedIds, "genai.retrieved_ids": q.retrievedIds, "genai.top_score": q.topScore,
        "genai.hidden_count": q.hiddenCount, "genai.answered": q.answered, "app.persona": q.persona,
      },
      data_stream: { dataset: "genai_response" },
    } }],
  };
  return [
    ...(note ? [`# ${note}`, ""] : []),
    "# The quality ingest pipeline: sentiment, language, topic, OWASP checks, LLM judge",
    `POST _ingest/pipeline/${pipeline}/_simulate`,
    body(doc),
    "",
  ].join("\n");
}

const cut = (s: string, n: number) => Array.from(s.slice(0, n)).join("");

/** Dev Tools Console deep link that simulates the quality pipeline on this answer; long texts are truncated to fit. */
export function qualityDevToolsUrl(base: string, q: QualityInput, pipeline: string): string {
  const build = (x: QualityInput, note?: string) => `${base}${CONSOLE_PREFIX}${compressToEncodedURIComponent(qualityConsoleText(x, pipeline, note))}`;
  let url = build(q);
  if (url.length <= MAX_DEVTOOLS_URL_CHARS) return url;
  let keep = Math.max(q.prompt.length, q.response.length, q.context.length);
  while (keep > 0) {
    keep = Math.floor(keep * 0.8);
    const t = { ...q, prompt: cut(q.prompt, keep), response: cut(q.response, keep), context: cut(q.context, keep) };
    url = build(t, `Texts truncated to ${keep} characters each to fit the link. Paste the full text to try it in full.`);
    if (url.length <= MAX_DEVTOOLS_URL_CHARS) break;
  }
  return url;
}
