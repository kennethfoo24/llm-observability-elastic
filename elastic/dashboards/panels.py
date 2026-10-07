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
Q_PANELS = [
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
    "LLM05|Improper output handling|Markup scan in genai-quality; Security rule glassbox-llm05-unsafe-output",
    "LLM06|Excessive agency|Visibility only: gen_ai.response.model in traces",
    "LLM07|System prompt leakage|Canary token match in genai-quality; Security rule glassbox-llm07-system-prompt-leak",
    "LLM08|Vector and embedding weaknesses|Document level security plus hidden_count probe alert glassbox-restricted-probing",
    "LLM09|Misinformation|LLM judge faithfulness in genai-quality; alert glassbox-low-faithfulness",
    "LLM10|Unbounded consumption|Token and cost attributes in traces; alert glassbox-llm-spend",
]
OWASP_PANELS = [
    Panel("LLM01 prompt injection: guardrail verdicts",
          f"{TRACES} AND attributes.app.guardrail.verdict IS NOT NULL | STATS requests = COUNT(*) BY verdict = attributes.app.guardrail.verdict | LIMIT 10",
          "bar", "verdict", "requests"),
    Panel("LLM02 PII in responses",
          f"{RESP} | WHERE output_reasons == \"pii_in_response\" | STATS pii_responses = COUNT(*)",
          "metric", "pii_responses", "pii_responses"),
    Panel("LLM05 unsafe markup in responses",
          f"{RESP} | WHERE output_reasons == \"unsafe_markup\" | STATS unsafe_responses = COUNT(*)",
          "metric", "unsafe_responses", "unsafe_responses"),
    Panel("LLM07 system prompt leaks",
          f"{RESP} | WHERE output_reasons == \"system_prompt_leak\" | STATS leaks = COUNT(*)",
          "metric", "leaks", "leaks"),
    Panel("LLM08 restricted topic probes by persona",
          f"{RESP} | WHERE quality.hidden_count > 0 | STATS probes = COUNT(*) BY persona = quality.persona | SORT probes DESC | LIMIT 10",
          "bar", "persona", "probes"),
    Panel("LLM09 low faithfulness answers",
          f"{RESP} | WHERE quality.low_faithfulness == true | STATS low_faithfulness = COUNT(*)",
          "metric", "low_faithfulness", "low_faithfulness"),
    Panel("LLM10 total spend (last 24 hours)",
          f"{TRACES} AND @timestamp > NOW() - 24 hours AND attributes.app.genai.cost_usd IS NOT NULL | STATS spend_usd = SUM(attributes.app.genai.cost_usd)",
          "metric", "spend_usd", "spend_usd"),
    Panel("LLM03 and LLM06 visibility only: model usage",
          f"{TRACES} AND attributes.gen_ai.response.model IS NOT NULL | STATS requests = COUNT(*) BY model = attributes.gen_ai.response.model | SORT requests DESC | LIMIT 10",
          "bar", "model", "requests"),
    Panel("OWASP risk to Elastic control",
          "ROW m = [" + ", ".join(f'"{r}"' for r in _MAPPING) + "] | MV_EXPAND m | "
          'DISSECT m "%{risk}|%{title}|%{control}" | EVAL covered = 1 | KEEP risk, title, control, covered',
          "table", "risk", "covered", cols=("risk", "title", "control", "covered"), index="traces-generic.otel-default"),
]

QUALITY_DASHBOARD = Dashboard("glassbox-quality", "Glass Box: Conversation quality",
                              "Answer rate, sentiment, language, topic and judge scores for the HR assistant.",
                              tuple(Q_PANELS))
OWASP_DASHBOARD = Dashboard("glassbox-owasp", "Glass Box: OWASP LLM Top 10 coverage",
                            "Live evidence per OWASP LLM risk and the Elastic control behind it.",
                            tuple(OWASP_PANELS))
OVERVIEW_DASHBOARD = Dashboard("glassbox-overview", "Glass Box: LLM observability",
                               "Cost, tokens, guardrails and latency for the Foo Corp HR assistant.", tuple(PANELS))
DASHBOARDS = [OVERVIEW_DASHBOARD, QUALITY_DASHBOARD, OWASP_DASHBOARD]
