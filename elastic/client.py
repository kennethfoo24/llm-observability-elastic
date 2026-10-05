import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "elasticsearch.txt").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if " " not in k.strip():
                out[k.strip()] = v.strip()
    return out


class Project:
    """One Elastic Serverless project. Credentials come from the gitignored elasticsearch.txt and are never printed."""

    def __init__(self, name: str, env: dict[str, str] | None = None, transport: httpx.BaseTransport | None = None):
        p = name.upper()
        env = env or _read_env()
        self.name = name
        self._es, self._kb = env[f"{p}_ELASTICSEARCH"].rstrip("/"), env[f"{p}_KIBANA"].rstrip("/")
        self.otlp = env.get(f"{p}_OPENTELEMETRY", "").rstrip("/")
        self._key = env[f"{p}_API_KEY"]
        self._http = httpx.Client(transport=transport, timeout=60.0)

    @property
    def hosts(self) -> tuple[str, str]:
        return self._es, self._kb

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"ApiKey {self._key}", "kbn-xsrf": "true", "x-elastic-internal-origin": "kibana"}

    def _call(self, base: str, method: str, path: str, body=None):
        kw = {"json": body} if body is not None else {}
        r = self._http.request(method, base + path, headers=self._headers(), **kw)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    def es(self, method: str, path: str, json=None):  # noqa: A002
        return self._call(self._es, method, path, json)

    def kb(self, method: str, path: str, json=None):  # noqa: A002
        return self._call(self._kb, method, path, json)

    def kb_import(self, ndjson: str):
        r = self._http.post(self._kb + "/api/saved_objects/_import?overwrite=true", headers=self._headers(),
                            files={"file": ("glassbox.ndjson", ndjson.encode(), "application/ndjson")})
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text[:300]
