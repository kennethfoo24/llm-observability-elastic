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
