"""General usage alert rules for every Elastic Serverless project (Observability, Security, Search); not specific to this app.

Billing itself is not readable with a project API key, so these watch the sources of the bill: AI usage (LLM calls and
tokens in `.kibana-inference-token-usage*`, written by Kibana for every Elastic managed inference call), workflow
executions (`.workflows-executions`, billed per run) and ingested documents. All are ES|QL `.es-query` rules built with
cost_alert.esql_rule_body and email once per day while active. `unmapped_fields="nullify"` makes a rule return no rows
instead of an error in a project where an index or field does not exist yet (for example no AI usage so far).
A rule needs a stable `BY` key (a constant `scope` when there is nothing to group on): Kibana builds the alert id from the
row's key columns, and a changing number there makes every run a new alert that bypasses the 24 hour throttle. Thresholds are parameters of each spec (apply.py --alert-override RULE_ID=VALUE)."""
from dataclasses import dataclass

from .cost_alert import esql_rule_body

NOTIFY_EMAIL = "kenneth.foo@elastic.co"
EMAIL_CONNECTOR_ID = "Elastic-Cloud-SMTP"      # preconfigured in every serverless project
PROJECTS = ("observability", "security", "search")
PREFIX = 'SET unmapped_fields="nullify"; '
TOKENS = "FROM .kibana-inference-token-usage*"
STREAMS = "FROM logs-*,metrics-*,traces-*"
EVERYTHING = "FROM *,-.*"                      # every non-hidden index, including custom indices


@dataclass(frozen=True)
class UsageSpec:
    rule_id: str
    name: str
    default: float              # the threshold the rule ships with
    interval: str
    window_hours: int
    time_field: str
    build: "callable"           # (threshold) -> esql


SPECS: list[UsageSpec] = [
    UsageSpec("usage-ai-tokens-day", "Usage: AI tokens above budget in 24 hours", 50_000_000, "15m", 24, "@timestamp",
              lambda n: f"{TOKENS} | WHERE @timestamp > NOW() - 24 hours | "
                        "EVAL scope = \"all AI usage\" | "
                        f"STATS tokens = SUM(token_usage.total_tokens) BY scope | WHERE tokens > {int(n)}"),
    UsageSpec("usage-ai-tokens-burst", "Usage: AI token burst in 1 hour (one model and feature)", 10_000_000, "5m", 1, "@timestamp",
              lambda n: f"{TOKENS} | WHERE @timestamp > NOW() - 1 hour | "
                        "STATS tokens = SUM(token_usage.total_tokens) BY model = model.model_id, feature = inference.feature_id | "
                        f"WHERE tokens > {int(n)} | LIMIT 10"),
    UsageSpec("usage-ai-calls-burst", "Usage: AI call rate runaway in 1 hour (one feature)", 2000, "5m", 1, "@timestamp",
              lambda n: f"{TOKENS} | WHERE @timestamp > NOW() - 1 hour | "
                        f"STATS calls = COUNT(*) BY feature = inference.feature_id | WHERE calls > {int(n)} | LIMIT 10"),
    UsageSpec("usage-ai-new-model", "Usage: a new AI model started being used", 0, "15m", 168, "@timestamp",
              lambda n: f"{TOKENS} | WHERE @timestamp > NOW() - 7 days | "
                        "STATS first_seen = MIN(@timestamp), calls = COUNT(*) BY model = model.model_id | "
                        "WHERE first_seen > NOW() - 1 hour | LIMIT 10"),
    UsageSpec("usage-workflow-runs", "Usage: workflow executions above budget in 24 hours (one workflow)", 1000, "15m", 24, "startedAt",
              lambda n: "FROM .workflows-executions | WHERE startedAt > NOW() - 24 hours | "
                        f"STATS runs = COUNT(*) BY workflow = workflowId | WHERE runs > {int(n)} | LIMIT 10"),
    UsageSpec("usage-ingest-total", "Usage: ingested documents above budget in 24 hours", 100_000_000, "1h", 24, "@timestamp",
              lambda n: f"{EVERYTHING} | WHERE @timestamp > NOW() - 24 hours | EVAL scope = \"all indices\" | STATS docs = COUNT(*) BY scope | WHERE docs > {int(n)}"),
    UsageSpec("usage-ingest-dataset", "Usage: one data stream above 20M documents in 24 hours", 20_000_000, "1h", 24, "@timestamp",
              lambda n: f"{STREAMS} | WHERE @timestamp > NOW() - 24 hours | "
                        "EVAL dataset = TO_STRING(data_stream.dataset) | "   # the field has conflicting types in some projects
                        f"STATS docs = COUNT(*) BY dataset | WHERE docs > {int(n)} | SORT docs DESC | LIMIT 10"),
]
BY_ID = {s.rule_id: s for s in SPECS}
# The rules this module replaced (app-specific names); apply deletes them when present.
RETIRED_IDS = ("glassbox-usage-tokens-day", "glassbox-usage-tokens-burst", "glassbox-usage-new-model",
               "glassbox-usage-workflow-runs", "glassbox-usage-ingest-total", "glassbox-usage-ingest-dataset")


def email_action() -> dict:
    return {
        "id": EMAIL_CONNECTOR_ID, "group": "query matched",
        "params": {"to": [NOTIFY_EMAIL], "subject": "[Elastic usage alert] {{rule.name}}",
                   "message": "{{rule.name}} is active in {{rule.spaceId}}.\n\n{{context.message}}\n\nOpen the rule: {{rule.url}}"},
        "frequency": {"summary": False, "notify_when": "onThrottleInterval", "throttle": "24h"},
    }


def rule_body(spec: UsageSpec, threshold: float | None = None) -> dict:
    n = spec.default if threshold is None else threshold
    body = esql_rule_body(spec.name, PREFIX + spec.build(n), ["usage", "billing"], spec.interval, spec.window_hours)
    body["params"]["timeField"] = spec.time_field
    body["actions"] = [email_action()]
    return body


def all_rules(overrides: dict[str, float] | None = None) -> dict[str, dict]:
    overrides = overrides or {}
    return {s.rule_id: rule_body(s, overrides.get(s.rule_id)) for s in SPECS}
