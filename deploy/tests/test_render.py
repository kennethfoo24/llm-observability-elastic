import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(*args):
    return subprocess.run([sys.executable, str(ROOT / "deploy" / "render.py"), *args], capture_output=True, text=True)


def test_render_substitutes_all_placeholders(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("image: ${IMAGE}\nhost: ${HOST}\n")
    r = _run(str(f), "--set", "IMAGE=repo/app@sha256:abc", "--set", "HOST=1-2-3-4.sslip.io")
    assert r.returncode == 0 and "image: repo/app@sha256:abc" in r.stdout and "host: 1-2-3-4.sslip.io" in r.stdout


def test_render_fails_loudly_on_a_missing_value(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("image: ${IMAGE}\nhost: ${HOST}\n")
    r = _run(str(f), "--set", "IMAGE=x")
    assert r.returncode != 0 and "HOST" in r.stderr


def test_render_refuses_secret_objects_and_never_echoes_values(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("apiVersion: v1\nkind: Secret\nstringData: {k: ${V}}\n")
    r = _run(str(f), "--set", "V=hunter2hunter2")
    assert r.returncode != 0 and "hunter2" not in r.stderr and r.stdout == ""


def test_render_rejects_malformed_set(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("x: 1\n")
    assert _run(str(f), "--set", "NOEQUALS").returncode != 0
