"""Fleet payloads and an idempotent installer for the gcp_vertexai integration (metrics only).

Credentials: no key is embedded. The metrics input runs on Application Default Credentials
(Workload Identity on the agent pod). Only the policy named `glassbox-gcp` / `glassbox-vertexai` is ever created.
"""
from elastic.client import Project

PACKAGE = "gcp_vertexai"
VERSION = "1.5.0"
POLICY_NAME = "glassbox-gcp"
PACKAGE_POLICY_NAME = "glassbox-vertexai"


def agent_policy_body() -> dict:
    return {"name": POLICY_NAME, "namespace": "default", "description": "Glass Box: Vertex AI metrics (single agent)",
            "monitoring_enabled": ["logs", "metrics"]}


def inputs_from_manifest(item: dict) -> dict:
    """Inputs map from the installed manifest: ONLY gcp_vertexai.metrics is enabled; the audit-log (Pub/Sub) and
    prompt/response (BigQuery) inputs and streams are explicitly disabled."""
    inputs: dict = {}
    by_input: dict[str, list[str]] = {}
    for ds in item.get("data_streams", []):
        for s in ds.get("streams", []):
            by_input.setdefault(s["input"], []).append(ds["dataset"])
    for tpl in item["policy_templates"]:
        for inp in tpl["inputs"]:
            metrics_input = tpl.get("data_streams") == ["metrics"]
            streams = {}
            for ds in by_input.get(inp["type"], []):
                if ds.split(".", 1)[-1] not in tpl.get("data_streams", []):
                    continue
                on = metrics_input and ds == "gcp_vertexai.metrics"
                streams[ds] = {"enabled": on, **({"vars": {"period": "60s"}} if on else {})}
            inputs[f"{tpl['name']}-{inp['type']}"] = {"enabled": metrics_input, "streams": streams}
    return inputs


def package_policy_body(policy_id: str, project_id: str, version: str, inputs_template: dict) -> dict:
    return {"name": PACKAGE_POLICY_NAME, "description": "Glass Box: Vertex AI metrics via Application Default Credentials",
            "namespace": "default", "policy_ids": [policy_id],
            "package": {"name": PACKAGE, "version": version},
            "vars": {"project_id": project_id},
            "inputs": inputs_template}


def _ok(resp, what: str):
    status, body = resp
    if status >= 300:
        msg = body.get("message", "") if isinstance(body, dict) else ""
        raise RuntimeError(f"{what}: HTTP {status} {msg[:400]}")
    return body


def install_vertex(p: Project, gcp_project: str) -> tuple[str, str]:
    """Install the package, create the agent + package policy if absent, return (fleet_url, enrollment_token) in memory only."""
    s, body = p.kb("GET", f"/api/fleet/epm/packages/{PACKAGE}/{VERSION}")
    if s >= 300:
        raise RuntimeError(f"package manifest: HTTP {s}")
    if body["item"].get("status") != "installed":
        _ok(p.kb("POST", f"/api/fleet/epm/packages/{PACKAGE}/{VERSION}", {"force": False}), "package install")
        body = _ok(p.kb("GET", f"/api/fleet/epm/packages/{PACKAGE}/{VERSION}"), "package manifest")
    item = body["item"]

    pols = _ok(p.kb("GET", "/api/fleet/agent_policies?perPage=200"), "list agent policies")["items"]
    pol = next((x for x in pols if x["name"] == POLICY_NAME), None)
    if pol is None:
        pol = _ok(p.kb("POST", "/api/fleet/agent_policies?sys_monitoring=false", agent_policy_body()), "create agent policy")["item"]
    pid = pol["id"]

    pps = _ok(p.kb("GET", "/api/fleet/package_policies?perPage=200"), "list package policies")["items"]
    if not any(x["name"] == PACKAGE_POLICY_NAME and pid in (x.get("policy_ids") or []) for x in pps):
        _ok(p.kb("POST", "/api/fleet/package_policies",
                 package_policy_body(pid, gcp_project, VERSION, inputs_from_manifest(item))), "create package policy")

    keys = _ok(p.kb("GET", f"/api/fleet/enrollment_api_keys?perPage=200&kuery=policy_id:{pid}"), "list enrollment keys")["items"]
    key = next((k for k in keys if k.get("policy_id") == pid and k.get("active")), None)
    if key is None:
        key = _ok(p.kb("POST", "/api/fleet/enrollment_api_keys", {"policy_id": pid, "name": "glassbox-gcp-agent"}), "create enrollment key")["item"]
    hosts = _ok(p.kb("GET", "/api/fleet/fleet_server_hosts"), "fleet hosts")["items"]
    host = next((h for h in hosts if h.get("is_default")), hosts[0])
    return host["host_urls"][0], key["api_key"]


def main(argv=None) -> int:
    """`python -m elastic.fleet --env-file PATH [--gcp-project elastic-sa]`: write fleet_url/enrollment_token to a mode-600 env file (never printed)."""
    import argparse
    import os

    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--gcp-project", default="elastic-sa")
    a = ap.parse_args(argv)
    url, token = install_vertex(Project("observability"), a.gcp_project)
    fd = os.open(a.env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"fleet_url={url}\nenrollment_token={token}\n")
    print("fleet package + agent policy ready; Secret input written (values not shown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
