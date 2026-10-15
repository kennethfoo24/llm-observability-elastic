from elastic import apply
from elastic.rules import usage_alerts as u


def test_every_usage_rule_is_general_and_emails_once_a_day():
    rules = u.all_rules()
    assert len(rules) == 7 and set(rules) == set(u.BY_ID)
    for rid, b in rules.items():
        assert rid.startswith("usage-") and "glassbox" not in rid and "glassbox" not in str(b["tags"])
        assert b["rule_type_id"] == ".es-query" and b["params"]["searchType"] == "esqlQuery"
        assert b["params"]["esqlQuery"]["esql"].startswith('SET unmapped_fields="nullify"; ')
        a = b["actions"][0]
        assert a["id"] == u.EMAIL_CONNECTOR_ID and a["params"]["to"] == ["kenneth.foo@elastic.co"]
        assert a["frequency"] == {"summary": False, "notify_when": "onThrottleInterval", "throttle": "24h"}


def test_thresholds_are_parameters_and_the_default_ships():
    q = u.all_rules({"usage-ai-tokens-day": 1})["usage-ai-tokens-day"]["params"]["esqlQuery"]["esql"]
    assert "tokens > 1" in q
    assert "tokens > 50000000" in u.all_rules()["usage-ai-tokens-day"]["params"]["esqlQuery"]["esql"]


def test_queries_cover_ai_workflow_and_ingest_sources():
    r = u.all_rules()
    esql = {k: v["params"]["esqlQuery"]["esql"] for k, v in r.items()}
    assert ".kibana-inference-token-usage*" in esql["usage-ai-tokens-burst"]
    assert "COUNT(*) BY feature" in esql["usage-ai-calls-burst"] and "BY model = model.model_id" in esql["usage-ai-new-model"]
    assert ".workflows-executions" in esql["usage-workflow-runs"] and r["usage-workflow-runs"]["params"]["timeField"] == "startedAt"
    assert "FROM *,-." in esql["usage-ingest-total"] and "TO_STRING(data_stream.dataset)" in esql["usage-ingest-dataset"]


def test_retired_app_specific_rules_are_not_recreated():
    assert not set(u.RETIRED_IDS) & set(u.BY_ID)
    assert all(i.startswith("glassbox-usage-") for i in u.RETIRED_IDS)


def test_apply_usage_alerts_deletes_retired_and_upserts_all(monkeypatch):
    seen = []
    monkeypatch.setattr(apply, "_delete_rule", lambda p, rid, dry: seen.append(("del", rid)))
    monkeypatch.setattr(apply, "_upsert_rule", lambda p, rid, body, dry: seen.append(("up", rid)))
    apply.apply_usage_alerts(object(), True)
    assert [x for x in seen if x[0] == "del"] == [("del", i) for i in u.RETIRED_IDS]
    assert [x[1] for x in seen if x[0] == "up"] == list(u.BY_ID)


def test_every_rule_groups_by_a_stable_key_so_the_daily_throttle_holds():
    # Kibana builds the alert id from the row's key columns; a changing total there re-fires the email every run.
    for rid, b in u.all_rules().items():
        esql = b["params"]["esqlQuery"]["esql"]
        stats = esql.split("STATS ", 1)[1].split(" | ", 1)[0]
        assert " BY " in stats, rid
        assert "BY scope" in stats or any(k in stats for k in ("model", "feature", "workflow", "dataset")), rid
