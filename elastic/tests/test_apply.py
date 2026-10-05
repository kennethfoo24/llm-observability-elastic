import json

import httpx

from elastic.apply import apply_project
from elastic.client import Project


def _project(handler, name="observability"):
    p = name.upper()
    return Project(name, env={
        f"{p}_ELASTICSEARCH": "http://es", f"{p}_KIBANA": "http://kb",
        f"{p}_API_KEY": "SECRET", f"{p}_OPENTELEMETRY": "http://otlp"},
        transport=httpx.MockTransport(handler))


def test_dry_run_makes_no_write_calls_and_prints_no_key(capsys):
    writes = []

    def handler(req):
        if req.method != "GET":
            writes.append((req.method, req.url.path))
        return httpx.Response(404, json={})

    apply_project(_project(handler), cost_threshold=0.25, dry_run=True)
    apply_project(_project(handler, "security"), cost_threshold=0.25, dry_run=True)
    assert writes == []
    out = capsys.readouterr().out
    assert "SECRET" not in out and "create" in out


def test_apply_is_idempotent_and_updates_existing_rules_in_place(capsys):
    calls, bodies = [], {}

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "PUT" and "alerting" in req.url.path:
            bodies["rule"] = json.loads(req.content)
        if req.method == "GET" and "logs@custom" in req.url.path:
            return httpx.Response(200, json={"logs@custom": {"processors": [{"set": {"field": "x", "value": 1}}]}})
        if req.method == "GET" and "/api/alerting/rule/glassbox-llm-spend" in req.url.path:
            return httpx.Response(200, json={"id": "glassbox-llm-spend"})
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    apply_project(_project(handler), cost_threshold=0.25, dry_run=False)
    assert ("PUT", "/_ingest/pipeline/genai-guardrail") in calls
    assert ("PUT", "/api/alerting/rule/glassbox-llm-spend") in calls          # updated, not duplicated
    assert not any(m == "POST" and p.startswith("/api/alerting/rule/glassbox-llm-spend") for m, p in calls)
    assert "rule_type_id" not in bodies["rule"] and "consumer" not in bodies["rule"]
    assert ("POST", "/api/saved_objects/_import") in calls
    assert "rule glassbox-llm-spend: update" in capsys.readouterr().out


def test_missing_rule_is_created_with_post():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "GET" and "/api/alerting/rule/" in req.url.path:
            return httpx.Response(404, json={})
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    apply_project(_project(handler), cost_threshold=0.25, dry_run=False)
    assert ("POST", "/api/alerting/rule/glassbox-llm-spend") in calls


def test_security_project_creates_or_updates_the_detection_rule_by_rule_id():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path, req.url.query.decode()))
        if req.method == "GET" and req.url.path == "/api/detection_engine/rules":
            return httpx.Response(200, json={"rule_id": "glassbox-flagged-prompts"})
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    apply_project(_project(handler, "security"), cost_threshold=0.25, dry_run=False)
    assert ("PUT", "/api/detection_engine/rules", "") in calls
    assert not any(m == "POST" and p == "/api/detection_engine/rules" for m, p, _ in calls)
    assert not any("alerting" in p or "saved_objects" in p for _, p, _ in calls)


def test_hook_merge_never_drops_existing_processors():
    sent = {}

    def handler(req):
        if req.method == "GET" and "logs@custom" in req.url.path:
            return httpx.Response(200, json={"logs@custom": {"processors": [{"set": {"field": "x", "value": 1}}]}})
        if req.method == "PUT" and "logs@custom" in req.url.path:
            sent["body"] = json.loads(req.content)
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    apply_project(_project(handler), cost_threshold=0.25, dry_run=False)
    procs = sent["body"]["processors"]
    assert procs[0] == {"set": {"field": "x", "value": 1}} and any("pipeline" in p for p in procs)
