import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
K8S = ROOT / "deploy" / "k8s"
FILES = sorted(K8S.glob("*.yaml"))
SETS = {"IMAGE": "example/app@sha256:0", "HOST": "1-2-3-4.sslip.io", "PROJECT": "elastic-sa", "STATIC_IP_NAME": "glassbox-ip"}


def _render():
    args = [sys.executable, str(ROOT / "deploy" / "render.py"), *map(str, FILES)]
    for k, v in SETS.items():
        args += ["--set", f"{k}={v}"]
    r = subprocess.run(args, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


TEXT = _render()
DOCS = [d for d in yaml.safe_load_all(TEXT) if d]
SECRETISH = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|ApiKey\s+[A-Za-z0-9=_\-]{20,}|-----BEGIN [A-Z ]+KEY)")


def _find(kind, name):
    return next(d for d in DOCS if d["kind"] == kind and d["metadata"]["name"] == name)


def test_render_is_valid_yaml_with_no_leftover_placeholders():
    assert DOCS and all("kind" in d and "apiVersion" in d for d in DOCS)
    assert not re.search(r"\$\{[A-Z_]+\}", TEXT)


def test_every_object_is_in_genai_demo_only():
    for d in DOCS:
        if d["kind"] == "Namespace":
            assert d["metadata"]["name"] == "genai-demo"
        else:
            assert d["metadata"].get("namespace") == "genai-demo", (d["kind"], d["metadata"]["name"])
    assert "opentelemetry-operator-system.svc" in TEXT  # only as the collector client endpoint
    for d in DOCS:
        assert d["metadata"].get("namespace") not in ("opentelemetry-operator-system", "o11y-metrics")


def test_no_collector_and_no_secret_objects_or_material():
    assert not [d for d in DOCS if d["kind"] in ("Secret", "DaemonSet", "ConfigMap", "OpenTelemetryCollector")]
    assert not SECRETISH.search(TEXT)
    assert not [d for d in DOCS if d["kind"] == "Deployment" and "collector" in d["metadata"]["name"]]


def test_app_pod_is_hardened_and_wired():
    dep = _find("Deployment", "glassbox")
    assert dep["spec"]["replicas"] <= 2
    spec = dep["spec"]["template"]["spec"]
    c = spec["containers"][0]
    assert spec["serviceAccountName"] == "glassbox"
    sc = spec["securityContext"]
    assert sc["runAsNonRoot"] is True and sc["runAsUser"] == 10001 and sc["seccompProfile"]["type"] == "RuntimeDefault"
    csc = c["securityContext"]
    assert csc["readOnlyRootFilesystem"] is True and csc["allowPrivilegeEscalation"] is False
    assert csc["capabilities"]["drop"] == ["ALL"]
    assert {"tmp"} <= {v["name"] for v in spec["volumes"] if "emptyDir" in v}
    assert any(m["mountPath"] == "/tmp" for m in c["volumeMounts"])
    assert c["resources"]["requests"] and c["resources"]["limits"]
    assert c["readinessProbe"]["httpGet"]["path"] == "/healthz" and c["livenessProbe"]["httpGet"]["path"] == "/healthz"
    env = {e["name"]: e for e in c["env"]}
    assert env["TRUSTED_PROXY_HOPS"]["value"] == "1"
    assert env["OTEL_SERVICE_NAME"]["value"] == "glassbox-backend"
    assert env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"]["value"] == "SPAN_ONLY"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"]["value"] == "http://opentelemetry-kube-stack-daemon-collector.opentelemetry-operator-system.svc.cluster.local:4318"
    for name in ("OBS_ES_URL", "OBS_ES_ADMIN_KEY", "OBS_ES_GUARDRAIL_KEY", "APP_PASSWORD", "GEMMA_API_KEY",
                 "GUARDRAIL_LOG_OBS_ENDPOINT", "GUARDRAIL_LOG_OBS_KEY", "GUARDRAIL_LOG_SEC_ENDPOINT", "GUARDRAIL_LOG_SEC_KEY"):
        assert "secretKeyRef" in env[name]["valueFrom"], name
    ksa = _find("ServiceAccount", "glassbox")
    assert ksa["metadata"]["annotations"]["iam.gke.io/gcp-service-account"] == "glassbox-app@elastic-sa.iam.gserviceaccount.com"
    svc = _find("Service", "glassbox")
    assert svc["metadata"]["annotations"]["cloud.google.com/neg"] == '{"ingress": true}'


def test_env_names_match_settings():
    cfg = (ROOT / "backend" / "app" / "config.py").read_text()
    fields = set(re.findall(r"^    ([a-z_]+): ", cfg, re.M))
    c = _find("Deployment", "glassbox")["spec"]["template"]["spec"]["containers"][0]
    for e in c["env"]:
        n = e["name"]
        if not n.startswith(("OTEL_", "POD_", "NODE_")):
            assert n.lower() in fields, n


def test_ingress_annotations_and_configs():
    a = _find("Ingress", "glassbox")["metadata"]["annotations"]
    assert a["kubernetes.io/ingress.global-static-ip-name"] == "glassbox-ip"
    assert a["networking.gke.io/managed-certificates"] == "glassbox-cert"
    assert a["kubernetes.io/ingress.class"] == "gce"
    assert a["networking.gke.io/v1beta1.FrontendConfig"] == "glassbox"
    bc = _find("BackendConfig", "glassbox")["spec"]
    assert bc["timeoutSec"] == 100 and bc["healthCheck"]["requestPath"] == "/healthz"
    assert _find("FrontendConfig", "glassbox")["spec"]["redirectToHttps"]["enabled"] is True
    assert _find("ManagedCertificate", "glassbox-cert")["spec"]["domains"] == ["1-2-3-4.sslip.io"]


def test_trafficgen_is_suspended_capped_and_hardened():
    cj = _find("CronJob", "glassbox-trafficgen")["spec"]
    assert cj["suspend"] is True and cj["concurrencyPolicy"] == "Forbid" and cj["timeZone"] == "Asia/Singapore"
    assert cj["schedule"] == "*/5 7-21 * * *"
    job = cj["jobTemplate"]["spec"]
    assert job["activeDeadlineSeconds"] <= 600 and job["backoffLimit"] == 0
    pod = job["template"]["spec"]
    c = pod["containers"][0]
    assert c["command"] == ["python", "-m", "trafficgen"]
    env = {e["name"]: e for e in c["env"]}
    assert int(env["MAX_REQUESTS"]["value"]) == 1 and "secretKeyRef" in env["APP_PASSWORD"]["valueFrom"]
    assert pod["securityContext"]["runAsNonRoot"] is True and pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    csc = c["securityContext"]
    assert csc["readOnlyRootFilesystem"] is True and csc["allowPrivilegeEscalation"] is False and csc["capabilities"]["drop"] == ["ALL"]
