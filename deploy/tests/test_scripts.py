import re
import subprocess
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


def test_bash_syntax_ok():
    for p in SCRIPTS:
        assert subprocess.run(["bash", "-n", str(p)]).returncode == 0, p.name


def test_dry_run_modes_do_not_mutate():
    env = {"DRY_RUN": "1", "PATH": "/usr/bin:/bin"}
    r = subprocess.run(["bash", str(ROOT / "deploy/scripts/create_secrets.sh")], env={**env, "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}, capture_output=True, text=True)
    assert r.returncode == 0 and "glog_obs_key" in r.stdout and "namespace=genai-demo" in r.stdout
