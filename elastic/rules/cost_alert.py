RULE_ID = "glassbox-llm-spend"


def rule_body(threshold_usd: float, window_hours: int = 1) -> dict:
    unit = "hour" if window_hours == 1 else "hours"
    esql = (
        'FROM traces-generic.otel-default | '
        f'WHERE service.name == "glassbox-backend" AND @timestamp > NOW() - {window_hours} {unit} '
        'AND attributes.app.genai.cost_usd IS NOT NULL | '
        f'STATS spend = SUM(attributes.app.genai.cost_usd) | WHERE spend > {threshold_usd}'
    )
    return {
        "name": "Glass Box: LLM spend above threshold",
        "rule_type_id": ".es-query", "consumer": "alerts",
        "schedule": {"interval": "1m"},
        "tags": ["glassbox", "cost", "llm"],
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


def update_body(body: dict) -> dict:
    """Kibana's update API rejects rule_type_id and consumer (immutable)."""
    return {k: v for k, v in body.items() if k not in ("rule_type_id", "consumer")}
