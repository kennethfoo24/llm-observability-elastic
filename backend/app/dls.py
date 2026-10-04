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
            # FLS hides non-granted fields from queries, not just _source. Grant content fields
            # so catalog role can search by content; app always filters _source to exclude them.
            "field_security": {"grant": ["title", "classification", "allowed_roles", "content", "content_semantic"]},
        }],
    }
}


def load_keys(path: str) -> dict[str, str]:
    return json.loads(Path(path).read_text())
