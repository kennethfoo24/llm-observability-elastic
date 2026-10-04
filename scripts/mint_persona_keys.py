# NOTE: fails with a project API key (see docs/p0-results.md Section C); run with a credential that can create keys, or paste the same role descriptors into Kibana Dev Tools and write the encoded keys to backend/secrets/persona_keys.json

import json
import sys
from pathlib import Path

from elasticsearch import Elasticsearch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import Settings  # noqa: E402
from app.dls import CATALOG_ROLE_DESCRIPTOR, persona_role_descriptor  # noqa: E402
from app.personas import PERSONAS  # noqa: E402

s = Settings()
es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
out_path = Path(__file__).resolve().parent.parent / "backend" / s.persona_keys_path
out_path.parent.mkdir(parents=True, exist_ok=True)

try:
    for old in es.security.get_api_key(name="glassbox-*").get("api_keys", []):
        es.security.invalidate_api_key(ids=[old["id"]])

    keys = {}
    jobs = [(p.id, persona_role_descriptor(p.role)) for p in PERSONAS] + [("catalog", CATALOG_ROLE_DESCRIPTOR)]
    for name, descriptor in jobs:
        resp = es.security.create_api_key(name=f"glassbox-{name}", role_descriptors=descriptor, expiration="90d")
        keys[name] = resp["encoded"]
    out_path.write_text(json.dumps(keys))
    out_path.chmod(0o600)
    print("minted keys for:", ", ".join(keys), "->", out_path.name)
except Exception as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
