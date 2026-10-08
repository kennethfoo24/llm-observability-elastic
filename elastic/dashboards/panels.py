from dataclasses import dataclass

SVC = 'service.name == "glassbox-backend" AND attributes.app.genai.cost_usd IS NOT NULL'
# Bucket follows the dashboard time range (Lens supplies ?_tstart / ?_tend).
BUCKET = "BUCKET(@timestamp, 50, ?_tstart, ?_tend)"


@dataclass(frozen=True)
class Panel:
    title: str
    esql: str
    chart: str      # "line" | "bar" | "metric"
    x: str
    y: str
    split: str | None = None
    extra_y: tuple[str, ...] = ()
    cols: tuple[str, ...] = ()     # "table" only: all columns in display order (x is the first, y the numeric one)
    index: str | None = None       # override for queries without FROM (static ROW tables)
    kinds: tuple[tuple[str, str], ...] = ()    # "table": column name -> date | number | boolean (default string)
    widths: tuple[tuple[str, int], ...] = ()   # "table": column name -> pixel width
    wide: bool = False             # full width row (w=48) and tall (h=14)


@dataclass(frozen=True)
class Dashboard:
    id: str
    title: str
    description: str
    panels: tuple["Panel", ...]


PANELS = [
    Panel("LLM spend over time by model",
          f"FROM traces-generic.otel-default | WHERE {SVC} | STATS spend = SUM(attributes.app.genai.cost_usd) "
          f"BY bucket = {BUCKET}, model = attributes.app.genai.model | SORT bucket",
          "line", "bucket", "spend", "model"),
    Panel("Average cost per request by persona",
          f"FROM traces-generic.otel-default | WHERE {SVC} | STATS avg_cost = AVG(attributes.app.genai.cost_usd) "
          "BY persona = attributes.app.persona | SORT avg_cost DESC | LIMIT 10",
          "bar", "persona", "avg_cost"),
    Panel("Total spend (selected range)",
          f"FROM traces-generic.otel-default | WHERE {SVC} | STATS total = SUM(attributes.app.genai.cost_usd)",
          "metric", "total", "total"),
    Panel("Tokens by model",
          f"FROM traces-generic.otel-default | WHERE {SVC} | STATS input = SUM(attributes.app.genai.input_tokens), "
          "output = SUM(attributes.app.genai.output_tokens) BY model = attributes.app.genai.model | LIMIT 10",
          "bar", "model", "input", None, ("output",)),
    Panel("Requests by engine",
          f"FROM traces-generic.otel-default | WHERE {SVC} | STATS requests = COUNT(*) "
          "BY engine = attributes.app.genai.engine | LIMIT 5",
          "bar", "engine", "requests"),
    Panel("Guardrail verdicts by outcome",
          f"FROM traces-generic.otel-default | WHERE {SVC} | STATS requests = COUNT(*) "
          "BY verdict = attributes.app.guardrail.verdict | LIMIT 10",
          "bar", "verdict", "requests"),
    # attributes.security is a flattened field, so its verdict sub-key is not addressable in ES|QL:
    # this panel counts guardrail log rows over time; the per-verdict split is the traces panel above.
    Panel("Guardrail prompt logs over time",
          "FROM logs-genai_guardrail* | "
          f"STATS prompts = COUNT(*) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "prompts"),
    # ES|QL duration on traces is nanoseconds.
    Panel("Request latency by stage (p95, ms)",
          'FROM traces-generic.otel-default | WHERE service.name == "glassbox-backend" AND '
          '(name IN ("guardrail.check", "retrieval.hybrid", "prompt.build") OR STARTS_WITH(name, "chat ")) | '
          'EVAL stage = CASE(STARTS_WITH(name, "chat "), "chat (LLM call)", name), '
          "ms = duration / 1000000.0 | "
          "STATS p95_ms = PERCENTILE(ms, 95) BY stage | LIMIT 10",
          "bar", "stage", "p95_ms"),
]


# ---------------------------------------------------------------- Conversation quality (typed genai_response fields)
RESP = "FROM logs-genai_response*"
_FLAG_ESQL = (
    "EVAL f1 = CASE(output_verdict == \"FLAGGED\", COALESCE(MV_CONCAT(output_reasons, \"+\"), \"flagged\"), \"\"), "
    "f2 = CASE(quality.off_topic == true, \"off_topic\", \"\"), "
    "f3 = CASE(quality.lang_mismatch == true, \"lang_mismatch\", \"\"), "
    "f4 = CASE(quality.low_faithfulness == true, \"low_faithfulness\", \"\"), "
    "f5 = CASE(quality.user_sentiment == \"negative\", \"negative_sentiment\", \"\"), "
    "f6 = CASE(quality.answered == false, \"unanswered\", \"\"), "
    "joined = TRIM(CONCAT(f1, \" \", f2, \" \", f3, \" \", f4, \" \", f5, \" \", f6)) | "
    "EVAL flag = CASE(joined == \"\", \"none\", joined)")
Q_PANELS = [
    Panel("Answered prompts, responses and flags",
          f"{RESP} | SORT @timestamp DESC | LIMIT 100 | {_FLAG_ESQL} | "
          "RENAME @timestamp AS time, quality.persona AS persona, quality.prompt_text AS prompt, "
          "quality.response_text AS response, quality.user_sentiment AS sentiment, quality.answered AS answered, "
          "quality.faithfulness AS faithfulness, quality.relevance AS relevance | "
          "KEEP time, persona, prompt, response, flag, sentiment, answered, faithfulness, relevance",
          "table", "time", "flag",
          cols=("time", "persona", "prompt", "response", "flag", "sentiment", "answered", "faithfulness", "relevance"),
          kinds=(("time", "date"), ("answered", "boolean"), ("faithfulness", "number"), ("relevance", "number")),
          widths=(("time", 170), ("persona", 90), ("prompt", 320), ("response", 520), ("flag", 220)), wide=True),
    Panel("Blocked and flagged prompts (guardrail)",
          'FROM traces-generic.otel-default | WHERE service.name == "glassbox-backend" AND name == "guardrail.check" '
          'AND attributes.guardrail.verdict == "FLAGGED" | SORT @timestamp DESC | LIMIT 100 | '
          "RENAME @timestamp AS time, attributes.guardrail.prompt_text AS prompt, attributes.guardrail.reasons AS reasons, "
          "attributes.guardrail.injection_score AS injection_score, trace.id AS trace_id | "
          "KEEP time, prompt, reasons, injection_score, trace_id",
          "table", "time", "prompt", cols=("time", "prompt", "reasons", "injection_score", "trace_id"),
          kinds=(("time", "date"), ("injection_score", "number")),
          widths=(("time", 170), ("prompt", 520), ("reasons", 220), ("trace_id", 260)), wide=True),
    Panel("Answered vs unanswered over time",
          f"{RESP} | WHERE quality.answered IS NOT NULL | EVAL status = CASE(quality.answered, \"answered\", \"unanswered\") | "
          f"STATS responses = COUNT(*) BY bucket = {BUCKET}, status | SORT bucket",
          "line", "bucket", "responses", "status"),
    Panel("Top unanswered prompts",
          f"{RESP} | WHERE quality.answered == false | STATS unanswered = COUNT(*) BY prompt = quality.prompt_text.keyword "
          "| SORT unanswered DESC | LIMIT 10",
          "bar", "prompt", "unanswered"),
    Panel("User sentiment split (LLM judge)",
          f"{RESP} | WHERE quality.user_sentiment IS NOT NULL | STATS prompts = COUNT(*) BY sentiment = quality.user_sentiment | LIMIT 5",
          "bar", "sentiment", "prompts"),
    Panel("Language mismatch count",
          f"{RESP} | WHERE quality.lang_mismatch == true | STATS mismatches = COUNT(*)",
          "metric", "mismatches", "mismatches"),
    Panel("Topic distribution",
          f"{RESP} | WHERE quality.topic IS NOT NULL | STATS prompts = COUNT(*) BY topic = quality.topic | SORT prompts DESC | LIMIT 10",
          "bar", "topic", "prompts"),
    Panel("Off topic rate over time (percent)",
          f"{RESP} | WHERE quality.off_topic IS NOT NULL | EVAL off_flag = CASE(quality.off_topic, 1.0, 0.0) | "
          f"STATS off_topic_pct = AVG(off_flag) * 100.0 BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "off_topic_pct"),
    Panel("Average faithfulness over time (1 to 5)",
          f"{RESP} | WHERE quality.faithfulness IS NOT NULL | STATS avg_faithfulness = AVG(quality.faithfulness) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "avg_faithfulness"),
    Panel("Low faithfulness answers over time",
          f"{RESP} | WHERE quality.low_faithfulness == true | STATS low_faithfulness = COUNT(*) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "low_faithfulness"),
    Panel("Average judge relevance (1 to 5)",
          f"{RESP} | WHERE quality.relevance IS NOT NULL | STATS avg_relevance = AVG(quality.relevance)",
          "metric", "avg_relevance", "avg_relevance"),
    Panel("Flagged responses by reason",
          f"{RESP} | WHERE output_verdict == \"FLAGGED\" | MV_EXPAND output_reasons | STATS flagged = COUNT(*) BY reason = output_reasons | LIMIT 10",
          "bar", "reason", "flagged"),
]

# ---------------------------------------------------------------- OWASP LLM Top 10 coverage
TRACES = 'FROM traces-generic.otel-default | WHERE service.name == "glassbox-backend"'
_MAPPING = [
    "LLM01|Prompt injection|DeBERTa classifier in the genai-guardrail ingest pipeline; rule Glass Box: flagged LLM prompt",
    "LLM02|Sensitive information disclosure|Regex and NER on the response in genai-quality; Security rule glassbox-llm02-pii-in-response",
    "LLM03|Supply chain|Visibility only: gen_ai.response.model in traces",
    "LLM04|Data and model poisoning|genai-doc-scan fingerprint and DeBERTa on documents (hr-kb-staging demo); alert glassbox-doc-integrity",
    "LLM05|Improper output handling|Markup scan in genai-quality; Security rule glassbox-llm05-unsafe-output",
    "LLM06|Excessive agency|Visibility only: gen_ai.response.model in traces",
    "LLM07|System prompt leakage|Canary token match in genai-quality; Security rule glassbox-llm07-system-prompt-leak",
    "LLM08|Vector and embedding weaknesses|Document level security plus alert glassbox-restricted-probing on unanswered queries that matched restricted documents",
    "LLM09|Misinformation|LLM judge faithfulness in genai-quality; alert glassbox-low-faithfulness",
    "LLM10|Unbounded consumption|Token and cost attributes in traces; alert glassbox-llm-spend",
]
OWASP_PANELS = [
    Panel("LLM01 prompt injection: guardrail verdicts",
          f"{TRACES} AND attributes.app.guardrail.verdict IS NOT NULL | STATS requests = COUNT(*) BY verdict = attributes.app.guardrail.verdict | LIMIT 10",
          "bar", "verdict", "requests"),
    Panel("LLM02 PII in responses",
          f"{RESP} | WHERE MV_CONTAINS(output_reasons, \"pii_in_response\") | STATS pii_responses = COUNT(*)",
          "metric", "pii_responses", "pii_responses"),
    Panel("LLM05 unsafe markup in responses",
          f"{RESP} | WHERE MV_CONTAINS(output_reasons, \"unsafe_markup\") | STATS unsafe_responses = COUNT(*)",
          "metric", "unsafe_responses", "unsafe_responses"),
    Panel("LLM07 system prompt leaks",
          f"{RESP} | WHERE MV_CONTAINS(output_reasons, \"system_prompt_leak\") | STATS leaks = COUNT(*)",
          "metric", "leaks", "leaks"),
    Panel("LLM08 restricted topic attempts by persona",
          f"{RESP} | WHERE quality.answered == false AND quality.hidden_count > 0 | STATS attempts = COUNT(*) BY persona = quality.persona | SORT attempts DESC | LIMIT 10",
          "bar", "persona", "attempts"),
    Panel("LLM09 low faithfulness answers",
          f"{RESP} | WHERE quality.low_faithfulness == true | STATS low_faithfulness = COUNT(*)",
          "metric", "low_faithfulness", "low_faithfulness"),
    Panel("LLM10 total spend (last 24 hours)",
          f"{TRACES} AND @timestamp > NOW() - 24 hours AND attributes.app.genai.cost_usd IS NOT NULL | STATS spend_usd = SUM(attributes.app.genai.cost_usd)",
          "metric", "spend_usd", "spend_usd"),
    Panel("LLM03 and LLM06 visibility only: model usage",
          f"{TRACES} AND attributes.gen_ai.response.model IS NOT NULL | STATS requests = COUNT(*) BY model = attributes.gen_ai.response.model | SORT requests DESC | LIMIT 10",
          "bar", "model", "requests"),
    Panel("Documents flagged or changed (LLM04)",
          'FROM hr-kb-staging | WHERE doc_scan.scanned_at > NOW() - 24 hours AND (doc_scan.verdict == "FLAGGED" OR doc_scan.fingerprint != doc_scan.baseline_fingerprint) | STATS docs = COUNT(*)',
          "metric", "docs", "docs"),
    Panel("OWASP risk to Elastic control",
          "ROW m = [" + ", ".join(f'"{r}"' for r in _MAPPING) + "] | MV_EXPAND m | "
          'DISSECT m "%{risk}|%{title}|%{control}" | EVAL scope = CASE(STARTS_WITH(control, \"Visibility only\"), \"visibility only\", \"controlled\") | KEEP risk, title, control, scope',
          "table", "risk", "scope", cols=("risk", "title", "control", "scope"), index="traces-generic.otel-default"),
]

QUALITY_DASHBOARD = Dashboard("glassbox-quality", "Glass Box: Conversation quality",
                              "Answer rate, sentiment, language, topic and judge scores for the HR assistant.",
                              tuple(Q_PANELS))
OWASP_DASHBOARD = Dashboard("glassbox-owasp", "Glass Box: OWASP LLM Top 10 coverage",
                            "Live evidence per OWASP LLM risk and the Elastic control behind it.",
                            tuple(OWASP_PANELS))
OVERVIEW_DASHBOARD = Dashboard("glassbox-overview", "Glass Box: LLM observability",
                               "Cost, tokens, guardrails and latency for the Foo Corp HR assistant.", tuple(PANELS))
# ---------------------------------------------------------------- Gemma (vLLM) via the Fleet Prometheus integration
# Counters are of ES|QL type `counter` (no MAX/MIN), so TO_DOUBLE first; per bucket MAX-MIN is the increase.
# The vLLM histograms are the legacy `histogram` type, which ES|QL cannot aggregate: no latency panel.
GM = "FROM metrics-prometheus.collector-*"
_GEN = "`prometheus.vllm:generation_tokens_total.counter`"
_PRM = "`prometheus.vllm:prompt_tokens_total.counter`"
_REQ = "`prometheus.vllm:request_success_total.counter`"
GEMMA_PANELS = [
    Panel("Gemma generated tokens per bucket",
          f"{GM} | WHERE {_GEN} IS NOT NULL | EVAL v = TO_DOUBLE({_GEN}) | STATS gen_tokens = MAX(v) - MIN(v) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "gen_tokens"),
    Panel("Gemma prompt tokens per bucket",
          f"{GM} | WHERE {_PRM} IS NOT NULL | EVAL v = TO_DOUBLE({_PRM}) | STATS prompt_tokens = MAX(v) - MIN(v) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "prompt_tokens"),
    Panel("Gemma requests finished (selected range)",
          f"{GM} | WHERE {_REQ} IS NOT NULL | EVAL v = TO_DOUBLE({_REQ}) | STATS d = MAX(v) - MIN(v) BY reason = prometheus.labels.finished_reason | STATS requests = SUM(d)",
          "metric", "requests", "requests"),
    Panel("Gemma running and waiting requests",
          f"{GM} | WHERE `prometheus.vllm:num_requests_running.value` IS NOT NULL | STATS running = MAX(`prometheus.vllm:num_requests_running.value`), "
          f"waiting = MAX(`prometheus.vllm:num_requests_waiting.value`) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "running", None, ("waiting",)),
    Panel("Gemma KV cache usage (percent)",
          f"{GM} | WHERE `prometheus.vllm:kv_cache_usage_perc.value` IS NOT NULL | STATS cache_pct = MAX(`prometheus.vllm:kv_cache_usage_perc.value`) * 100 BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "cache_pct"),
    Panel("Gemma scrape samples (zero while the VM is stopped)",
          f"{GM} | STATS samples = COUNT(*) BY bucket = {BUCKET} | SORT bucket",
          "line", "bucket", "samples"),
]
GEMMA_DASHBOARD = Dashboard("glassbox-gemma", "Glass Box: Gemma (vLLM)",
                            "Self-hosted Gemma on vLLM: tokens, requests, queue and KV cache from the Fleet Prometheus integration. Data exists only while the VM runs.",
                            tuple(GEMMA_PANELS))
DASHBOARDS = [OVERVIEW_DASHBOARD, QUALITY_DASHBOARD, OWASP_DASHBOARD, GEMMA_DASHBOARD]
