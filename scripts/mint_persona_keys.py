# NOTE: fails with a project API key (see docs/p0-results.md Section C); run with a credential that can create keys, or paste the same role descriptors into Kibana Dev Tools and write the encoded keys to backend/secrets/persona_keys.json

import json
import os
import sys
from pathlib import Path

from elasticsearch import Elasticsearch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import Settings  # noqa: E402
from app.dls import CATALOG_ROLE_DESCRIPTOR, persona_role_descriptor  # noqa: E402
from app.personas import PERSONAS  # noqa: E402


def mint(es, out_path: Path) -> list[str]:
    """Mint persona API keys and write to file. Returns list of persona names."""
    # Get old keys before creating new ones
    old_key_ids = {old["id"] for old in es.security.get_api_key(name="glassbox-*", owner=True).get("api_keys", [])}

    # Create all new keys first
    keys = {}
    new_key_ids = set()
    try:
        jobs = [(p.id, persona_role_descriptor(p.role)) for p in PERSONAS] + [("catalog", CATALOG_ROLE_DESCRIPTOR)]
        for name, descriptor in jobs:
            resp = es.security.create_api_key(name=f"glassbox-{name}", role_descriptors=descriptor, expiration="90d")
            keys[name] = resp["encoded"]
            new_key_ids.add(resp["id"])

        # Write keys safely with 0o600 mode
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        # Ensure file has 0o600 even if it pre-existed as 0644 (must be before fdopen closes it)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(keys, f)

        # Only after successful write, invalidate old ones
        to_delete = old_key_ids - new_key_ids
        if to_delete:
            es.security.invalidate_api_key(ids=list(to_delete))

        return list(keys.keys())
    except Exception:
        # Best-effort invalidate just-created keys on any failure
        if new_key_ids:
            try:
                es.security.invalidate_api_key(ids=list(new_key_ids))
            except Exception:
                pass
        raise


def main() -> int:
    """Build client and mint keys. Returns 0 on success, 1 on error."""
    try:
        s = Settings()
        es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
        out_path = Path(__file__).resolve().parent.parent / "backend" / s.persona_keys_path

        persona_names = mint(es, out_path)
        print("minted keys for:", ", ".join(persona_names), "->", out_path.name)
        return 0
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
