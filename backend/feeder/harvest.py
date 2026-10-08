"""Fetch sample events from Fleet and store them as committed JSON templates (runtime needs no Fleet access).

Usage: python -m feeder harvest --group ai     (admin key, local)
For every stream we GET /api/fleet/epm/packages/<pkg>/<ver>/data_stream/<dir>/sample_event.json (and the stream's
manifest.yml title for the record). Pipeline test inputs (_dev/test) are not served by Fleet for installed
packages, so sample_event.json is the template source. Templates are stored as
{"package","version","dir","dataset","type","sample": {...}} under feeder/templates/<package>/<dir>.json.
"""
from __future__ import annotations

import json

from . import catalog


def harvest(kb, group: str) -> list[str]:
    out = []
    for s in catalog.streams(group):
        st, body = kb("GET", f"/api/fleet/epm/packages/{s.package}/{s.version}/data_stream/{s.dir}/sample_event.json")
        if st != 200 or not isinstance(body, dict):
            out.append(f"MISSING {s.key} (status {st})")
            continue
        s.template_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"package": s.package, "version": s.version, "dir": s.dir, "dataset": s.dataset, "type": s.type, "sample": body}
        s.template_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        out.append(f"ok {s.key}")
    return out


def load_template(s: catalog.Stream) -> dict:
    """The stored sample_event.json for a stream (raises FileNotFoundError if harvest was not run)."""
    return json.loads(s.template_path.read_text())["sample"]
