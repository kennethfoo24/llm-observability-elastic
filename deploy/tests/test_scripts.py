import os
import re
import shutil
import subprocess

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "deploy" / "scripts").glob("*.sh"))

FORBIDDEN = [
    r"service-accounts\s+keys\s+create",
    r"firewall-rules",
    r"add-metadata",
    r"--metadata-from-file",
    r"git\s+push",
    r"(-n|--namespace)[ =]+(opentelemetry-operator-system|o11y-metrics)",
    r"--dry-run=server",
]


def test_scripts_exist():
    assert {p.name for p in SCRIPTS} >= {"_common.sh", "gcp_bootstrap.sh", "build_push.sh", "create_secrets.sh", "deploy.sh", "teardown.sh"}


def test_no_forbidden_commands_in_any_script():
    for p in SCRIPTS:
        text = p.read_text()
        for pat in FORBIDDEN:
            assert not re.search(pat, text), (p.name, pat)
        if p.name != "teardown.sh":
            assert not re.search(r"kubectl\s+(-n\s+\S+\s+)?delete\s+namespace", text), p.name


def test_every_entry_script_is_strict_guarded_and_dry_runnable():
    for p in SCRIPTS:
        text = p.read_text()
        assert "set -euo pipefail" in text, p.name
        if p.name != "_common.sh":
            assert "_common.sh" in text, p.name
            assert "guard_gcloud" in text or p.name == "create_secrets.sh", p.name
    common = (ROOT / "deploy" / "scripts" / "_common.sh").read_text()
    assert "DRY_RUN" in common and "elastic-sa" in common and "gke_${PROJECT_ID}_${ZONE}_${CLUSTER}" in common


def test_create_secrets_has_guards_and_reads_only_local_sources():
    t = (ROOT / "deploy" / "scripts" / "create_secrets.sh").read_text()
    assert "guard_kube" in t and "guard_gcloud" in t and 'die "namespace must be' in t
    assert "guardrail_log_keys.json" in t and "GLOG_OBS_KEY" in t and "GLOG_SEC_KEY" in t
    assert "--dry-run=client -o yaml | kubectl apply" in t
    assert "sec_kibana_url" in t and "SECURITY_KIBANA" in t
    assert "backend/secrets/system_prompt_canary.txt" in t and "token_hex(8)" in t and "'GBX-'" in t
    assert "printf 'system_prompt_canary=%s" in t and not re.search(r"echo[^\n]*\$SYSTEM_PROMPT_CANARY", t)


def test_app_manifest_wires_optional_security_kibana_url():
    m = (ROOT / "deploy" / "k8s" / "30-app.yaml").read_text()
    assert "SEC_KIBANA_URL" in m and "key: sec_kibana_url, optional: true" in m


def test_app_manifest_wires_optional_canary_secret():
    m = (ROOT / "deploy" / "k8s" / "30-app.yaml").read_text()
    assert "SYSTEM_PROMPT_CANARY" in m and "key: system_prompt_canary, optional: true" in m


def test_bash_syntax_ok():
    for p in SCRIPTS:
        assert subprocess.run(["bash", "-n", str(p)]).returncode == 0, p.name


def test_dry_run_modes_do_not_mutate():
    env = {"DRY_RUN": "1", "PATH": "/usr/bin:/bin"}
    r = subprocess.run(["bash", str(ROOT / "deploy/scripts/create_secrets.sh")], env={**env, "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}, capture_output=True, text=True)
    assert r.returncode == 0 and "glog_obs_key" in r.stdout and "system_prompt_canary" in r.stdout and "namespace=genai-demo" in r.stdout


def test_dry_run_value_is_validated():
    r = subprocess.run(["bash", str(ROOT / "deploy/scripts/create_secrets.sh")], env={"DRY_RUN": "yes", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.returncode != 0 and "DRY_RUN must be 0 or 1" in r.stderr


def test_secrets_never_pass_through_argv_and_teardown_waits():
    t = (ROOT / "deploy/scripts/create_secrets.sh").read_text()
    assert "--from-literal" not in t and "--from-env-file" in t and "umask 077" in t and "trap" in t
    td = (ROOT / "deploy/scripts/teardown.sh").read_text()
    assert "|| true" not in td.split("--all")[0] and "wait --for=delete pod" in td


def test_dockerignore_and_gcloudignore_exclude_secrets():
    for name in (".dockerignore", ".gcloudignore"):
        lines = {l.strip() for l in (ROOT / name).read_text().splitlines()}
        assert "elasticsearch.txt" in lines, name
        assert lines & {".env", "**/.env", "**/*.env", "*.env"}, name
        assert lines & {"backend/secrets", "**/secrets"}, name
        assert {"*-sa-key.json", "frontend/.env.local"} <= lines, name
    assert ".playwright-mcp" in {l.strip() for l in (ROOT / ".dockerignore").read_text().splitlines()}


def test_cloud_build_enables_buildkit_for_copy_chmod():
    text = (SCRIPTS[0].parent / "build_push.sh").read_text()
    assert 'DOCKER_BUILDKIT=1' in text


def test_gemma_script_safe_and_dry_runnable():
    p = ROOT / "deploy/scripts/gemma.sh"
    t = p.read_text()
    assert subprocess.run(["bash", "-n", str(p)]).returncode == 0
    for pat in FORBIDDEN + [r"set-metadata", r"\bset -x\b", r"\bcurl\b[^\n]*-v"]:
        assert not re.search(pat, t), pat
    assert "asia-southeast1-c" in t and "kenneth-gemma-llm" in t and "guard_gcloud" in t
    assert 'Bearer %s' in t and "-K -" in t  # key via stdin config, not argv
    gc = shutil.which("gcloud")
    if gc is None:
        pytest.skip("gcloud not installed")
    env = {**os.environ, "DRY_RUN": "1"}
    for sub, needle in (("start", "[dry-run] gcloud compute instances start"),
                        ("stop", "[dry-run] gcloud compute instances stop"), ("wait", "[dry-run] would poll")):
        r = subprocess.run(["bash", str(p), sub], env=env, capture_output=True, text=True)
        assert r.returncode == 0 and needle in r.stdout, (sub, r.stdout, r.stderr)
    r = subprocess.run(["bash", str(p), "bogus"], env=env, capture_output=True, text=True)
    assert r.returncode != 0


def test_demo_scripts_safe_and_dry_runnable():
    for name in ("demo_up.sh", "demo_down.sh"):
        p = ROOT / "deploy/scripts" / name
        t = p.read_text()
        assert subprocess.run(["bash", "-n", str(p)]).returncode == 0, name
        for pat in FORBIDDEN + [r"\bset -x\b", r"app_password\.txt\)"]:
            assert not re.search(pat, t), (name, pat)
        assert "guard_gcloud" in t and "guard_kube" in t and "set -euo pipefail" in t
        assert not re.search(r"cat\s+\S*app_password", t), name  # password is never read or printed
    assert "backend/secrets/app_password.txt" in (ROOT / "deploy/scripts/demo_up.sh").read_text()
    if shutil.which("gcloud") is None or shutil.which("kubectl") is None:
        pytest.skip("gcloud/kubectl not installed")
    env = {**os.environ, "DRY_RUN": "1"}
    r = subprocess.run(["bash", str(ROOT / "deploy/scripts/demo_up.sh"), "--gemma"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert '"suspend":false' in r.stdout.replace("\\", "") and "instances start" in r.stdout and "would poll" in r.stdout
    assert "see backend/secrets/app_password.txt" in r.stdout
    r = subprocess.run(["bash", str(ROOT / "deploy/scripts/demo_down.sh"), "--teardown"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert '"suspend":true' in r.stdout.replace("\\", "") and "instances stop" in r.stdout and "delete ingress" in r.stdout
    for name in ("demo_up.sh", "demo_down.sh"):
        assert subprocess.run(["bash", str(ROOT / "deploy/scripts" / name), "--bogus"], env=env, capture_output=True).returncode != 0


def test_gemma_stop_ssd_flag_follows_env():
    if shutil.which("gcloud") is None:
        pytest.skip("gcloud not installed")
    p = str(ROOT / "deploy/scripts/gemma.sh")
    base = {**os.environ, "DRY_RUN": "1"}
    base.pop("GEMMA_DISCARD_SSD", None)
    r = subprocess.run(["bash", p, "stop"], env=base, capture_output=True, text=True)
    assert "--discard-local-ssd=false" in r.stdout
    r = subprocess.run(["bash", p, "stop"], env={**base, "GEMMA_DISCARD_SSD": "1"}, capture_output=True, text=True)
    assert "--discard-local-ssd=true" in r.stdout
    r = subprocess.run(["bash", p, "stop"], env={**base, "GEMMA_DISCARD_SSD": "x"}, capture_output=True, text=True)
    assert r.returncode != 0


def test_teardown_offers_ip_release_and_no_script_mentions_the_removed_agent():
    for n in ("create_secrets.sh", "deploy.sh", "teardown.sh", "gcp_bootstrap.sh"):
        t = (ROOT / "deploy/scripts" / n).read_text()
        assert "WITH_AGENT" not in t and "elastic.fleet" not in t and "elastic-agent" not in t, n
    assert "addresses delete" in (ROOT / "deploy/scripts/teardown.sh").read_text()
