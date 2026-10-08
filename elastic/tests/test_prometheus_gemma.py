import httpx

from elastic import prometheus_gemma as pg
from elastic.client import Project

PW = "S3CRET-pw-value-xyz"
ITEM = {"status": "installed", "policy_templates": [{"name": "prometheus", "inputs": [{"type": "prometheus/metrics"}]}],
        "data_streams": [{"dataset": d, "streams": [{"input": "prometheus/metrics"}]}
                         for d in ("prometheus.collector", "prometheus.query", "prometheus.remote_write")]}


def _project(calls, existing=None):
    def handler(req):
        calls.append((req.method, req.url.path, req.content.decode()))
        p = req.url.path
        if p.startswith("/api/fleet/epm/packages"):
            return httpx.Response(200, json={"item": ITEM})
        if p == "/api/fleet/agent_policies":
            return httpx.Response(200, json={"items": [{"id": "pol-1", "name": "kubernetes-agent-policy"}, {"id": "x", "name": "other"}]})
        if p == "/api/fleet/package_policies" and req.method == "GET":
            return httpx.Response(200, json={"items": existing or []})
        return httpx.Response(200, json={"item": {}})
    env = {"OBSERVABILITY_ELASTICSEARCH": "https://es.example.test", "OBSERVABILITY_KIBANA": "https://kb.example.test",
           "OBSERVABILITY_API_KEY": "k"}
    return Project("observability", env=env, transport=httpx.MockTransport(handler))


def test_body_targets_only_gemma_host_and_collector_stream():
    body = pg.package_policy_body("pol-1", pg.inputs_from_manifest(ITEM, "llm.example.test", PW))
    st = body["inputs"]["prometheus-prometheus/metrics"]["streams"]
    assert st["prometheus.collector"]["enabled"] and not st["prometheus.query"]["enabled"] and not st["prometheus.remote_write"]["enabled"]
    v = st["prometheus.collector"]["vars"]
    assert v["hosts"] == ["https://llm.example.test"] and v["metrics_path"] == "/metrics" and v["username"] == "metrics"
    assert v["period"] == "60s" and v["timeout"] == "10s" and v["ssl.verification_mode"] == "full"
    assert body["policy_ids"] == ["pol-1"] and body["name"] == "glassbox-gemma-vllm"


def test_create_posts_once_to_the_kubernetes_policy_and_never_prints_password(capsys):
    calls = []
    assert pg.apply(_project(calls), "llm.example.test", PW) == "created"
    posts = [c for c in calls if c[0] == "POST" and c[1] == "/api/fleet/package_policies"]
    assert len(posts) == 1 and "pol-1" in posts[0][2]
    assert [c for c in calls if c[0] in ("PUT", "DELETE")] == []
    out = capsys.readouterr()
    assert PW not in out.out + out.err


def test_existing_policy_is_updated_by_name_and_dry_run_writes_nothing():
    calls = []
    assert pg.apply(_project(calls, [{"id": "pp-9", "name": "glassbox-gemma-vllm"}]), "h", PW) == "updated"
    assert any(c[0] == "PUT" and c[1].endswith("/pp-9") for c in calls)
    calls = []
    res = pg.apply(_project(calls), "h", PW, dry=True)
    assert "dry-run" in res and PW not in res and not [c for c in calls if c[0] in ("POST", "PUT")]


def test_refuses_when_agent_policy_missing():
    import pytest
    p = _project([])
    p._http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"item": ITEM, "items": []})))
    with pytest.raises(RuntimeError):
        pg.apply(p, "h", PW)


def test_gemma_host_comes_from_the_app_manifest():
    h = pg.gemma_host()
    assert h.endswith(".nip.io") and "/" not in h
