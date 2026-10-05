import httpx

from elastic.client import Project
from elastic.fleet import agent_policy_body, install_vertex, package_policy_body

ENV = {"OBS_ELASTICSEARCH": "https://es.example", "OBS_KIBANA": "https://kb.example", "OBS_API_KEY": "k"}


def test_agent_policy_is_dedicated_and_named():
    b = agent_policy_body()
    assert b["name"] == "glassbox-gcp" and b["namespace"] == "default" and b["monitoring_enabled"] == ["logs", "metrics"]


def test_package_policy_targets_vertex_ai_with_the_project_and_no_embedded_key():
    b = package_policy_body(policy_id="p1", project_id="elastic-sa", version="1.5.0", inputs_template={"gcp_vertexai-gcp": {}})
    assert b["package"] == {"name": "gcp_vertexai", "version": "1.5.0"} and b["policy_ids"] == ["p1"]
    assert "credentials_json" not in str(b) and "private_key" not in str(b) and "credentials_file" not in str(b)
    assert "elastic-sa" in str(b)


def test_install_is_idempotent_and_never_touches_other_policies():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        p, m = req.url.path, req.method
        if p.startswith("/api/fleet/epm/packages/gcp_vertexai") and m == "GET":
            return httpx.Response(200, json={"item": {"status": "installed", "policy_templates": [
                {"name": "t", "inputs": [{"type": "gcp/metrics"}], "data_streams": ["metrics"]}], "data_streams": []}})
        if p == "/api/fleet/agent_policies" and m == "GET":
            return httpx.Response(200, json={"items": [{"id": "other", "name": "kubernetes-agent-policy"}, {"id": "p1", "name": "glassbox-gcp"}]})
        if p == "/api/fleet/package_policies" and m == "GET":
            return httpx.Response(200, json={"items": [{"name": "glassbox-vertexai", "policy_ids": ["p1"]}]})
        if p == "/api/fleet/enrollment_api_keys" and m == "GET":
            return httpx.Response(200, json={"items": [{"id": "e1", "policy_id": "p1", "active": True, "api_key": "TOKEN"}]})
        if p == "/api/fleet/fleet_server_hosts":
            return httpx.Response(200, json={"items": [{"is_default": True, "host_urls": ["https://fleet.example:443"]}]})
        return httpx.Response(500, json={})

    proj = Project("obs", env=ENV, transport=httpx.MockTransport(handler))
    url, token = install_vertex(proj, "elastic-sa")
    assert url == "https://fleet.example:443" and token == "TOKEN"
    assert not [c for c in calls if c[0] in ("POST", "PUT", "DELETE") and c[1] in ("/api/fleet/agent_policies", "/api/fleet/package_policies")]


def test_only_the_metrics_stream_is_enabled():
    from elastic.fleet import inputs_from_manifest
    item = {"policy_templates": [
        {"name": "M", "data_streams": ["metrics"], "inputs": [{"type": "gcp/metrics"}]},
        {"name": "L", "data_streams": ["auditlogs", "prompt_response_logs"], "inputs": [{"type": "gcp/metrics"}, {"type": "gcp-pubsub"}]}],
        "data_streams": [{"dataset": "gcp_vertexai.metrics", "streams": [{"input": "gcp/metrics"}]},
                         {"dataset": "gcp_vertexai.prompt_response_logs", "streams": [{"input": "gcp/metrics"}]},
                         {"dataset": "gcp_vertexai.auditlogs", "streams": [{"input": "gcp-pubsub"}]}]}
    inp = inputs_from_manifest(item)
    assert inp["M-gcp/metrics"]["enabled"] and inp["M-gcp/metrics"]["streams"]["gcp_vertexai.metrics"]["enabled"]
    assert not inp["L-gcp/metrics"]["enabled"] and not inp["L-gcp-pubsub"]["enabled"]
    assert list(inp["M-gcp/metrics"]["streams"]) == ["gcp_vertexai.metrics"]
