"""Minimal Elasticsearch / Kibana clients. Credentials are never printed or logged.

KeyClient   : runtime client for the CronJob (env OBS_ES_URL + FEEDER_KEY, narrow write-only key).
AdminClient : local-only wrapper around elastic.client.Project("observability") (admin key) with ES and Kibana access.
Both expose es(method, path, json=None) -> (status, body) and bulk(lines) -> (status, body).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx


class MissingKey(RuntimeError):
    pass


def _bulk_body(lines: list[dict]) -> str:
    return "".join(json.dumps(x, separators=(",", ":"), default=str) + "\n" for x in lines)


class KeyClient:
    def __init__(self, url: str, key: str, transport: httpx.BaseTransport | None = None):
        self._url = url.rstrip("/")
        self._key = key
        self._http = httpx.Client(transport=transport, timeout=60.0)

    @classmethod
    def from_env(cls) -> "KeyClient":
        url, key = os.environ.get("OBS_ES_URL", ""), os.environ.get("FEEDER_KEY", "")
        if not url:
            raise MissingKey("OBS_ES_URL is not set (Secret glassbox-app key obs_es_url)")
        if not key:
            raise MissingKey("FEEDER_KEY is not set: create the narrow write-only key and store it as Secret glassbox-app key "
                             "feeder_key (docs/feeder.md, 'Creating the feeder key')")
        return cls(url, key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"ApiKey {self._key}", "x-elastic-internal-origin": "kibana"}

    def es(self, method: str, path: str, json: dict | None = None):  # noqa: A002
        kw = {"json": json} if json is not None else {}
        r = self._http.request(method, self._url + path, headers=self._headers(), **kw)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    def bulk(self, lines: list[dict]):
        h = {**self._headers(), "Content-Type": "application/x-ndjson"}
        r = self._http.post(self._url + "/_bulk?filter_path=errors,items.*.status,items.*.failure_store,items.*.error.type,items.*.error.reason",
                            headers=h, content=_bulk_body(lines))
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text[:300]


def local_feeder_client() -> KeyClient:
    """The narrow feeder key for LOCAL tests: OBSERVABILITY_FEEDER_API_KEY from the gitignored elasticsearch.txt
    (or env FEEDER_KEY). Never printed. The CronJob uses env OBS_ES_URL + FEEDER_KEY instead."""
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from elastic.client import _read_env  # noqa: PLC0415
    env = _read_env()
    key = os.environ.get("FEEDER_KEY") or env.get("OBSERVABILITY_FEEDER_API_KEY", "")
    if not key:
        raise MissingKey("no feeder key: set FEEDER_KEY or OBSERVABILITY_FEEDER_API_KEY in elasticsearch.txt")
    return KeyClient(env["OBSERVABILITY_ELASTICSEARCH"], key)


class AdminClient(KeyClient):
    """Admin key via elastic/client.py (local only, never in the container)."""

    def __init__(self, project: str = "observability"):
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from elastic.client import Project  # noqa: PLC0415 (lazy: not shipped in the image)
        self._p = Project(project)
        self._p._http.timeout = 300.0
        self._http = self._p._http
        self._url = self._p.hosts[0]

    def _headers(self) -> dict[str, str]:
        return self._p._headers()

    def kb(self, method: str, path: str, json: dict | None = None):  # noqa: A002
        return self._p.kb(method, path, json)
