import json
from pathlib import Path

from .index_def import INDEX_NAME


def persona_role_descriptor(role: str, index: str = INDEX_NAME) -> dict:
    return {
        role: {
            "cluster": ["monitor_inference"],
            "indices": [{
                "names": [index],
                "privileges": ["read"],
                "query": {"terms": {"allowed_roles": [role]}},
            }],
        }
    }


CATALOG_ROLE_DESCRIPTOR = {
    "catalog": {
        "cluster": ["monitor_inference"],
        "indices": [{
            "names": [INDEX_NAME],
            "privileges": ["read"],
            "field_security": {"grant": ["title", "classification", "allowed_roles"]},
        }],
    }
}


def load_keys(path: str) -> dict[str, str]:
    return json.loads(Path(path).read_text())
