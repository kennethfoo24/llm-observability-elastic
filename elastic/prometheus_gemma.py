"""Fleet package policy `glassbox-gemma-vllm`: the Prometheus integration scrapes the Gemma VM's vLLM /metrics.

ONE package policy is created (or updated by name) on the existing agent policy `kubernetes-agent-policy`
(the one elastic-agent-k8s uses). Nothing else in Fleet is touched. The metrics password is read from the
gitignored backend/secrets/gemma_metrics_password.txt and only ever sent in the request body; it is never
printed or logged. Run: python -m elastic.prometheus_gemma [--dry-run]
"""
import argparse
import re
import sys
from pathlib import Path

from elastic.client import Project

ROOT = Path(__file__).resolve().parent.parent
PACKAGE, VERSION = "prometheus", "1.24.4"
AGENT_POLICY_NAME = "kubernetes-agent-policy"
PACKAGE_POLICY_NAME = "glassbox-gemma-vllm"
PASSWORD_FILE = ROOT / "backend" / "secrets" / "gemma_metrics_password.txt"
DEPLOY_APP = ROOT / "deploy" / "k8s" / "30-app.yaml"
USERNAME = "metrics"
COLLECTOR_STREAM = "prometheus.collector"


def gemma_host(path: Path = DEPLOY_APP) -> str:
    """The Gemma host from the app's own GEMMA_BASE_URL (https://<host>/v1), without scheme or path."""
    m = re.search(r'GEMMA_BASE_URL, value: "https://([^/"]+)', path.read_text())
    if not m:
        raise SystemExit("GEMMA_BASE_URL not found in the app manifest")
    return m.group(1)


def read_password(path: Path = PASSWORD_FILE) -> str:
    try:
        pw = path.read_text().strip()
    except OSError:
        pw = ""
    if not pw:
        raise SystemExit("missing backend/secrets/gemma_metrics_password.txt (run deploy/scripts/gemma_metrics_lock.py apply)")
    return pw


def inputs_from_manifest(item: dict, host: str, password: str) -> dict:
    """Only prometheus.collector is enabled (query and remote_write streams off); the leader election var keeps
    it to one scraping agent."""
    inputs: dict = {}
    for tpl in item["policy_templates"]:
        for inp in tpl["inputs"]:
            streams = {}
            for ds in item["data_streams"]:
                for s in ds["streams"]:
                    if s["input"] != inp["type"]:
                        continue
                    on = ds["dataset"] == COLLECTOR_STREAM
                    entry: dict = {"enabled": on}
                    if on:
                        entry["vars"] = {
                            "hosts": [f"https://{host}"], "metrics_path": "/metrics", "period": "60s", "timeout": "10s",
                            "username": USERNAME, "password": password, "ssl.verification_mode": "full",
                            "leaderelection": True, "use_types": True, "rate_counters": True,
                            "data_stream.dataset": COLLECTOR_STREAM,
                            "metrics_filters.include": ["vllm:*"],
                        }
                    streams[ds["dataset"]] = entry
            inputs[f"{tpl['name']}-{inp['type']}"] = {"enabled": True, "streams": streams}
    return inputs


def package_policy_body(policy_id: str, inputs: dict) -> dict:
    return {"name": PACKAGE_POLICY_NAME, "description": "LLM Observability: Gemma vLLM metrics (password protected /metrics)",
            "namespace": "default", "policy_ids": [policy_id],
            "package": {"name": PACKAGE, "version": VERSION}, "inputs": inputs}


def _ok(resp, what: str):
    status, body = resp
    if status >= 300:
        msg = body.get("message", "") if isinstance(body, dict) else ""
        raise RuntimeError(f"{what}: HTTP {status} {msg[:300]}")
    return body


def apply(p: Project, host: str, password: str, dry: bool = False) -> str:
    """Create or update the package policy. Returns 'created', 'updated' or the dry-run action. Never prints the password."""
    body = _ok(p.kb("GET", f"/api/fleet/epm/packages/{PACKAGE}/{VERSION}"), "package manifest")
    if body["item"].get("status") != "installed":
        if dry:
            print(f"[dry-run] would install package {PACKAGE} {VERSION}")
        else:
            _ok(p.kb("POST", f"/api/fleet/epm/packages/{PACKAGE}/{VERSION}", {"force": False}), "package install")
            body = _ok(p.kb("GET", f"/api/fleet/epm/packages/{PACKAGE}/{VERSION}"), "package manifest")
    pols = _ok(p.kb("GET", "/api/fleet/agent_policies?perPage=200"), "list agent policies")["items"]
    pol = next((x for x in pols if x["name"] == AGENT_POLICY_NAME), None)
    if pol is None:
        raise RuntimeError(f"agent policy {AGENT_POLICY_NAME} not found; refusing to create one")
    payload = package_policy_body(pol["id"], inputs_from_manifest(body["item"], host, password))
    pps = _ok(p.kb("GET", "/api/fleet/package_policies?perPage=200"), "list package policies")["items"]
    existing = next((x for x in pps if x["name"] == PACKAGE_POLICY_NAME), None)
    action = "updated" if existing else "created"
    if dry:
        return f"[dry-run] would be {action} on agent policy {AGENT_POLICY_NAME}"
    if existing:
        _ok(p.kb("PUT", f"/api/fleet/package_policies/{existing['id']}", payload), "update package policy")
    else:
        _ok(p.kb("POST", "/api/fleet/package_policies", payload), "create package policy")
    return action


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    host = gemma_host()
    try:
        res = apply(Project("observability"), host, read_password(), a.dry_run)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"package policy {PACKAGE_POLICY_NAME}: {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
