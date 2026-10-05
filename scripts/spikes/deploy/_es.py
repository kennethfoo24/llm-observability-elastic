"""Tiny helper for spikes: authenticated JSON calls to a project (never prints keys)."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from app.envfile import parse_env_text  # noqa: E402

RAW = parse_env_text((ROOT / "elasticsearch.txt").read_text())


def call(project, svc, method, path, body=None, headers=None):
    base = RAW[f"{project.upper()}_{svc.upper()}"].rstrip("/")
    h = {"Authorization": "ApiKey " + RAW[f"{project.upper()}_API_KEY"], "Content-Type": "application/json", "kbn-xsrf": "true"}
    h.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
