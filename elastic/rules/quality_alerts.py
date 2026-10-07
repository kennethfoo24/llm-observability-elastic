"""Observability alert rules over the typed `genai_response` fields (see elastic/README.md).

All are ES|QL `.es-query` rules built with cost_alert.esql_rule_body: interval 5m, look-back 1h. Thresholds are
function parameters so a proof run can lower one temporarily (python -m elastic.apply --alert-override RULE_ID=VALUE)."""
from dataclasses import dataclass

from .cost_alert import esql_rule_body

BASE = "FROM logs-genai_response* | WHERE @timestamp > NOW() - 1 hour"


@dataclass(frozen=True)
class AlertSpec:
    rule_id: str
    name: str
    owasp: str
    default_min: float          # the threshold the rule ships with
    tags: tuple[str, ...]
    build: "callable"           # (threshold) -> esql


def _count_rule(condition: str):
    return lambda n: f"{BASE} AND {condition} | STATS hits = COUNT(*) | WHERE hits >= {int(n)}"


def _unanswered(rate_pct: float) -> str:
    return (f"{BASE} AND quality.answered IS NOT NULL | EVAL unanswered_flag = CASE(quality.answered == false, 1, 0) | "
            "STATS responses = COUNT(*), unanswered = SUM(unanswered_flag) | "
            f"EVAL unanswered_pct = TO_DOUBLE(unanswered) * 100.0 / TO_DOUBLE(responses) | "
            f"WHERE responses >= 5 AND unanswered_pct > {rate_pct}")


def _probing(n: float) -> str:
    # An attempt: the user got no usable answer (quality.answered == false) while restricted documents matched.
    # hidden_count counts catalog matches (RRF top 8), not relevance, so it is only meaningful together with answered == false.
    return (f"{BASE} AND quality.answered == false AND quality.hidden_count > 0 | "
            f"STATS probes = COUNT(*) BY persona = quality.persona | WHERE probes >= {int(n)} | LIMIT 10")


SPECS: list[AlertSpec] = [
    AlertSpec("glassbox-unanswered-rate", "Glass Box: Unanswered rate above 40 percent", "Quality", 40.0,
              ("quality", "unanswered"), _unanswered),
    AlertSpec("glassbox-negative-sentiment", "Glass Box: Negative user sentiment", "Quality", 3,
              ("quality", "sentiment"), _count_rule('quality.user_sentiment == "negative"')),
    AlertSpec("glassbox-low-faithfulness", "Glass Box: Low faithfulness answers", "OWASP LLM09", 2,
              ("owasp", "llm09", "faithfulness"), _count_rule("quality.low_faithfulness == true")),
    AlertSpec("glassbox-restricted-probing", "Glass Box: Restricted topic attempts", "OWASP LLM08", 3,
              ("owasp", "llm08", "probing"), _probing),
    AlertSpec("glassbox-off-topic", "Glass Box: Off topic prompts", "Quality", 3,
              ("quality", "off-topic"), _count_rule("quality.off_topic == true")),
    AlertSpec("glassbox-language-mismatch", "Glass Box: Language mismatch", "Quality", 2,
              ("quality", "language"), _count_rule("quality.lang_mismatch == true")),
]
BY_ID = {s.rule_id: s for s in SPECS}


def rule_body(rule_id: str, threshold: float | None = None) -> dict:
    s = BY_ID[rule_id]
    esql = s.build(s.default_min if threshold is None else threshold)
    return esql_rule_body(s.name, esql, ["glassbox", *s.tags], interval="5m", window_hours=1)


def all_rules(overrides: dict[str, float] | None = None) -> dict[str, dict]:
    return {s.rule_id: rule_body(s.rule_id, (overrides or {}).get(s.rule_id)) for s in SPECS}
