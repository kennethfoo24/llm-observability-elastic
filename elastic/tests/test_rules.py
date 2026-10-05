from elastic.rules.cost_alert import RULE_ID, rule_body, update_body
from elastic.rules.guardrail_detection import rule_body as detection_body


def test_cost_alert_is_an_esql_rule_summing_the_root_span_cost_attribute():
    b = rule_body(0.25)
    p = b["params"]
    assert b["rule_type_id"] == ".es-query" and b["consumer"] == "alerts" and RULE_ID == "glassbox-llm-spend"
    assert p["searchType"] == "esqlQuery"
    q = p["esqlQuery"]["esql"]
    assert 'service.name == "glassbox-backend"' in q and "SUM(attributes.app.genai.cost_usd)" in q
    assert "WHERE spend > 0.25" in q and "NOW() - 1 hour" in q
    assert b["schedule"]["interval"] == "1m" and "glassbox" in b["tags"]


def test_cost_alert_params_match_the_shape_this_kibana_returns_for_esql_rules():
    p = rule_body(0.25)["params"]
    # shape observed on an existing ES|QL rule in the project (GET /api/alerting/rules/_find)
    for key in ("searchType", "timeWindowSize", "timeWindowUnit", "threshold", "thresholdComparator", "size",
                "esqlQuery", "aggType", "groupBy", "termSize", "sourceFields", "timeField",
                "excludeHitsFromPreviousRun"):
        assert key in p, key
    assert p["aggType"] == "count" and p["groupBy"] == "row" and p["timeField"] == "@timestamp"


def test_cost_alert_threshold_and_window_are_parameters():
    q = rule_body(1.5, window_hours=6)["params"]["esqlQuery"]["esql"]
    assert "spend > 1.5" in q and "NOW() - 6 hours" in q


def test_update_body_drops_the_immutable_keys():
    u = update_body(rule_body(0.25))
    assert "rule_type_id" not in u and "consumer" not in u
    assert u["params"] == rule_body(0.25)["params"] and u["name"] == rule_body(0.25)["name"]


def test_detection_rule_targets_flagged_verdicts_and_is_deterministic():
    d = detection_body()
    assert d["rule_id"] == "glassbox-flagged-prompts" and d["type"] == "query" and d["language"] == "kuery"
    assert d["index"] == ["logs-genai_guardrail*"]
    assert d["query"] == 'attributes.security.threat_verdict : "FLAGGED"'
    assert d["severity"] in {"medium", "high"} and d["enabled"] is True
    assert d["alert_suppression"]["group_by"] == ["attributes.app.persona"]
