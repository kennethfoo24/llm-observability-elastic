RULE_ID = "glassbox-llm-spend"


def esql_rule_body(name: str, esql: str, tags: list[str], interval: str = "1m", window_hours: int = 1) -> dict:
    """Shared builder for every LLM Observability ES|QL `.es-query` rule (the query itself carries the look-back)."""
    return {
        "name": name,
        "rule_type_id": ".es-query", "consumer": "alerts",
        "schedule": {"interval": interval},
        "tags": tags,
        # Param shape copied from an existing ES|QL rule of this Kibana (9.6.0 serverless).
        "params": {
            "searchType": "esqlQuery", "esqlQuery": {"esql": esql},
            "timeField": "@timestamp", "timeWindowSize": window_hours, "timeWindowUnit": "h",
            "size": 1, "threshold": [0], "thresholdComparator": ">",
            "aggType": "count", "groupBy": "row", "termSize": 5,
            "excludeHitsFromPreviousRun": False, "sourceFields": [],
        },
        "actions": [],
    }


def rule_body(threshold_usd: float, window_hours: int = 1) -> dict:
    unit = "hour" if window_hours == 1 else "hours"
    esql = (
        'FROM traces-generic.otel-default | '
        f'WHERE service.name == "glassbox-backend" AND @timestamp > NOW() - {window_hours} {unit} '
        'AND attributes.app.genai.cost_usd IS NOT NULL | '
        f'STATS spend = SUM(attributes.app.genai.cost_usd) | WHERE spend > {threshold_usd}'
    )
    return esql_rule_body("LLM Observability: LLM spend above threshold", esql, ["glassbox", "cost", "llm"], "1m", window_hours)


def update_body(body: dict) -> dict:
    """Kibana's update API rejects rule_type_id and consumer (immutable)."""
    return {k: v for k, v in body.items() if k not in ("rule_type_id", "consumer")}
