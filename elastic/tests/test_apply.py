import json

import httpx

from elastic.apply import apply_project
from elastic.client import Project


DEFAULT_TEMPLATE = {"index_templates": [{"name": "logs-otel@template", "index_template": {
    "index_patterns": ["logs-*.otel-*"], "composed_of": ["logs@mappings", "otel@mappings", "ecs@mappings"],
    "priority": 120, "ignore_missing_component_templates": ["logs@custom"]}}]}


def _project(handler, name="observability"):
    inner = handler

    def handler(req):  # noqa: F811 - every fake cluster serves the (read-only) default otel template
        if req.method == "GET" and req.url.path == "/_index_template/logs-otel@template":
            return httpx.Response(200, json=DEFAULT_TEMPLATE)
        return inner(req)

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


def test_hook_get_failure_other_than_404_aborts_without_any_hook_put():
    import pytest

    for code in (401, 403, 500, 503):
        puts = []

        def handler(req, code=code):
            if req.method == "GET" and "logs@custom" in req.url.path:
                return httpx.Response(code, json={"error": "boom"})
            if req.method != "GET":
                puts.append(req.url.path)
            return httpx.Response(200, json={"acknowledged": True, "success": True})

        with pytest.raises(SystemExit):
            apply_project(_project(handler), cost_threshold=0.25, dry_run=False)
        assert not any("logs@custom" in p for p in puts), code


def test_hook_404_means_absent_and_creates_it():
    sent = {}

    def handler(req):
        if req.method == "GET" and "logs@custom" in req.url.path:
            return httpx.Response(404, json={})
        if req.method == "PUT" and "logs@custom" in req.url.path:
            sent["body"] = json.loads(req.content)
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    apply_project(_project(handler), cost_threshold=0.25, dry_run=False)
    assert [list(p) for p in sent["body"]["processors"]] == [["pipeline"], ["pipeline"]]


def test_rerun_with_hook_already_present_makes_no_hook_put_and_no_duplicate():
    from app.guardrail_pipeline import build_hook
    from app.quality_pipeline import build_quality_hook
    existing = build_quality_hook(build_hook({"processors": [{"set": {"field": "x", "value": 1}}]}))
    puts = []

    def handler(req):
        if req.method == "GET" and "logs@custom" in req.url.path:
            return httpx.Response(200, json={"logs@custom": {**existing, "created_date_millis": 1}})
        if req.method == "PUT" and "logs@custom" in req.url.path:
            puts.append(json.loads(req.content))
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    apply_project(_project(handler), cost_threshold=0.25, dry_run=False)
    assert puts == []
    assert len(build_quality_hook(build_hook(existing))["processors"]) == 3


def test_dashboard_import_failure_is_detected_from_parsed_json():
    import pytest

    def handler(req):
        if req.url.path == "/api/saved_objects/_import":
            return httpx.Response(200, json={"success": False, "errors": [{"id": "glassbox-overview"}]})
        return httpx.Response(200, json={"acknowledged": True})

    with pytest.raises(SystemExit):
        apply_project(_project(handler), cost_threshold=0.25, dry_run=False)


def test_project_flag_is_required_and_bare_run_writes_nothing():
    import subprocess
    import sys
    from elastic.client import ROOT
    r = subprocess.run([sys.executable, "-m", "elastic.apply"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "--project" in r.stderr and "pipeline" not in r.stdout


def test_install_pipeline_security_without_sec_env_fails_clearly(tmp_path):
    import os
    import subprocess
    import sys
    from elastic.client import ROOT
    env = {"PATH": os.environ["PATH"], "OBS_ES_URL": "http://x", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "http://y"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "install_pipeline.py"), "--project", "security"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and "SEC_ES_URL" in r.stderr and "Traceback" not in r.stderr.split("SEC_ES_URL")[0][-200:]
