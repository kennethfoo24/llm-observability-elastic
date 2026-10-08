"""Dashboard coverage report: which installed OOTB integration dashboards are EMPTY / PARTIAL / FILLED / STALE.

For each dashboard of every installed Fleet package we resolve its panels (lens, legacy visualizations, saved searches,
ES|QL, maps; by-value and by-reference), derive the data views and fields each panel reads, and check for the last
15 minutes and the last 7 days whether those data views have documents and every referenced field is populated.

Status (per dashboard, over the data panels it has):
  EMPTY    no panel is fully populated in the last 7 days
  PARTIAL  some, but not all, panels are fully populated in the last 7 days
  STALE    all panels populated within 7 days, but none populated in the last 15 minutes
  FILLED   all panels populated within 7 days and at least one populated in the last 15 minutes
  NO_DATA  the dashboard has no data panels (markdown, controls only)
Dashboard level query/filters and panel level query/filters from the saved objects are applied. Per column filters
inside lens formulas are not. Needs the admin key (read on data), so it runs locally only.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

WINDOWS = {"15m": "now-15m", "7d": "now-7d"}
_SKIP_FIELDS = {"___records___", "", None}


@dataclass
class Source:
    """One data read: an index pattern, the fields it needs, and the filters that scope it."""
    index: str
    fields: set[str] = field(default_factory=set)
    filters: list[dict] = field(default_factory=list)  # ES query clauses


@dataclass
class Panel:
    title: str
    kind: str
    sources: list[Source] = field(default_factory=list)
    esql: list[str] = field(default_factory=list)
    checked: bool = True  # False for panels we cannot analyse (vega, timelion, links, ...)


# ---------- filter conversion -------------------------------------------------------------------------------------

def _legacy_match(q: Any) -> Any:
    """Old saved filters hold {"match": {field: {"query": v, "type": "phrase"}}}, which current Elasticsearch rejects: use match_phrase."""
    if isinstance(q, dict) and set(q) == {"match"} and isinstance(q["match"], dict) and len(q["match"]) == 1:
        (field, v), = q["match"].items()
        if isinstance(v, dict) and v.get("type") == "phrase" and "query" in v:
            return {"match_phrase": {field: v["query"]}}
    return q


def filter_to_query(f: dict) -> dict | None:
    meta = f.get("meta") or {}
    if meta.get("disabled"):
        return None
    q: dict | None = None
    if meta.get("type") == "combined" and isinstance(meta.get("params"), list):
        parts = [x for x in (filter_to_query(p) for p in meta["params"]) if x]
        if parts:
            q = {"bool": {"should": parts, "minimum_should_match": 1}} if meta.get("relation") == "OR" else {"bool": {"filter": parts}}
    elif f.get("query"):
        q = _legacy_match(f["query"])
    elif meta.get("key") and isinstance(meta.get("params"), dict) and "query" in meta["params"]:
        q = {"match_phrase": {meta["key"]: meta["params"]["query"]}}
    elif meta.get("type") == "exists" and meta.get("key"):
        q = {"exists": {"field": meta["key"]}}
    if q is None:
        return None
    return {"bool": {"must_not": [q]}} if meta.get("negate") else q


def query_to_clause(q: Any) -> dict | None:
    if not isinstance(q, dict):
        return None
    text = q.get("query")
    if not isinstance(text, str) or not text.strip():
        return None
    if q.get("language") == "lucene":
        return {"query_string": {"query": text}}
    return {"kql": {"query": text}}


def scope_clauses(search_source: dict) -> list[dict]:
    out = [c for c in (filter_to_query(f) for f in search_source.get("filter") or []) if c]
    qc = query_to_clause(search_source.get("query"))
    return out + ([qc] if qc else [])


def _json(s: Any) -> dict:
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s) if s else {}
    except (TypeError, ValueError):
        return {}


# ---------- saved object resolution ------------------------------------------------------------------------------

class Resolver:
    def __init__(self, objects: dict[tuple[str, str], dict]):
        self.objects = objects  # (type, id) -> saved object

    def index_title(self, ref_id: str, adhoc: dict | None = None) -> tuple[str, set[str]]:
        """Return (index pattern, runtime field names) for a data view id."""
        if adhoc and ref_id in adhoc:
            a = adhoc[ref_id]
            return a.get("title", ref_id), set((a.get("runtimeFieldMap") or {}).keys())
        o = self.objects.get(("index-pattern", ref_id))
        if o:
            at = o.get("attributes", {})
            return at.get("title", ref_id), set(_json(at.get("runtimeFieldMap")).keys())
        return ref_id, set()

    def _ref(self, refs: list[dict], name: str) -> str | None:
        for r in refs or []:
            if r.get("name") == name:
                return r.get("id")
        return None

    # --- lens
    def lens(self, title: str, attrs: dict, extra_scope: list[dict]) -> Panel:
        state = attrs.get("state") or {}
        refs = list(attrs.get("references") or []) + list(state.get("internalReferences") or [])
        adhoc = state.get("adHocDataViews") or {}
        scope = list(extra_scope) + scope_clauses({"query": state.get("query"), "filter": state.get("filters")})
        panel = Panel(title, "lens")
        dsl = state.get("datasourceStates") or {}
        layers = {**((dsl.get("formBased") or {}).get("layers") or {}), **((dsl.get("indexpattern") or {}).get("layers") or {})}
        for lid, layer in layers.items():
            ref_id = layer.get("indexPatternId") or self._ref(refs, f"indexpattern-datasource-layer-{lid}")
            if not ref_id and len(adhoc) == 1:
                ref_id = next(iter(adhoc))
            if not ref_id:
                continue
            idx, runtime = self.index_title(ref_id, adhoc)
            cols = layer.get("columns") or {}
            fields = {c.get("sourceField") for c in cols.values() if isinstance(c, dict)} - _SKIP_FIELDS - runtime
            panel.sources.append(Source(idx, set(fields), list(scope)))
        for layer in ((dsl.get("textBased") or {}).get("layers") or {}).values():
            q = (layer.get("query") or {}).get("esql")
            if q:
                panel.esql.append(q)
        q = (state.get("query") or {}).get("esql") if isinstance(state.get("query"), dict) else None
        if q and q not in panel.esql:
            panel.esql.append(q)
        if not panel.sources and not panel.esql:
            panel.checked = False
        return panel

    # --- legacy visualization
    def visualization(self, title: str, attrs: dict, refs: list[dict], extra_scope: list[dict]) -> Panel:
        vis = _json(attrs.get("visState"))
        vtype = vis.get("type", "")
        params = vis.get("params") or {}
        panel = Panel(title, f"vis:{vtype}")
        if vtype == "metrics":  # TSVB
            idx = params.get("index_pattern") or "logs-*,metrics-*"
            if isinstance(idx, dict):
                idx = idx.get("id", "logs-*,metrics-*")
            fields: set[str] = set()
            for s in params.get("series") or []:
                for m in s.get("metrics") or []:
                    fields.add(m.get("field"))
                fields.add(s.get("terms_field"))
                if s.get("override_index_pattern") and s.get("series_index_string"):
                    panel.sources.append(Source(s["series_index_string"], {s.get("series_time_field") or "@timestamp"}, list(extra_scope)))
            if params.get("type") in ("table",):
                fields.add(params.get("pivot_id"))
            fields -= _SKIP_FIELDS
            panel.sources.append(Source(idx, fields, list(extra_scope)))
            return panel
        if vtype in ("vega",):
            spec = params.get("spec", "")
            idxs = set(re.findall(r'"?index"?\s*:\s*"([^"]+)"', spec))
            for i in idxs:
                panel.sources.append(Source(i, set(), list(extra_scope)))
            panel.checked = bool(idxs)
            return panel
        if vtype in ("markdown", "input_control_vis", "timelion", "tagcloud_unused"):
            panel.checked = False
            return panel
        ss = _json((attrs.get("kibanaSavedObjectMeta") or {}).get("searchSourceJSON"))
        idx_id = ss.get("index") if isinstance(ss.get("index"), str) else None
        idx_id = self._ref(refs, "kibanaSavedObjectMeta.searchSourceJSON.index") or idx_id
        scope = list(extra_scope) + scope_clauses(ss)
        if not idx_id:
            sid = self._ref(refs, "search_0")
            so = self.objects.get(("search", sid)) if sid else None
            if so:
                sss = _json((so.get("attributes", {}).get("kibanaSavedObjectMeta") or {}).get("searchSourceJSON"))
                idx_id = self._ref(so.get("references") or [], "kibanaSavedObjectMeta.searchSourceJSON.index")
                scope += scope_clauses(sss)
        fields = {a.get("params", {}).get("field") for a in vis.get("aggs") or [] if isinstance(a, dict)}
        fields.add(params.get("field"))
        fields -= _SKIP_FIELDS
        if not idx_id:
            panel.checked = False
            return panel
        idx, runtime = self.index_title(idx_id)
        panel.sources.append(Source(idx, fields - runtime, scope))
        return panel

    # --- saved search
    def search(self, title: str, attrs: dict, refs: list[dict], extra_scope: list[dict]) -> Panel:
        ss = _json((attrs.get("kibanaSavedObjectMeta") or {}).get("searchSourceJSON"))
        panel = Panel(title, "search")
        q = ss.get("query")
        if isinstance(q, dict) and q.get("esql"):
            panel.kind = "search:esql"
            panel.esql.append(q["esql"])
            return panel
        idx_id = self._ref(refs, "kibanaSavedObjectMeta.searchSourceJSON.index") or (ss.get("index") if isinstance(ss.get("index"), str) else None)
        if not idx_id:
            panel.checked = False
            return panel
        idx, runtime = self.index_title(idx_id)
        cols = {c for c in attrs.get("columns") or [] if isinstance(c, str) and c != "_source"} - runtime
        panel.sources.append(Source(idx, cols, list(extra_scope) + scope_clauses(ss)))
        return panel

    # --- map
    def map(self, title: str, attrs: dict, refs: list[dict], extra_scope: list[dict]) -> Panel:
        panel = Panel(title, "map")
        for layer in _json_list(attrs.get("layerListJSON")):
            sd = layer.get("sourceDescriptor") or {}
            pid = sd.get("indexPatternId")
            if pid:
                idx, _ = self.index_title(pid)
                panel.sources.append(Source(idx, {sd.get("geoField")} - _SKIP_FIELDS, list(extra_scope)))
        if not panel.sources:
            panel.checked = False
        return panel


def dashboard_panels(dash: dict, resolver: Resolver) -> list[Panel]:
    at = dash.get("attributes", {})
    refs = dash.get("references") or []
    scope = scope_clauses(_json((at.get("kibanaSavedObjectMeta") or {}).get("searchSourceJSON")))
    raw = at.get("panels") if isinstance(at.get("panels"), list) else _json_list(at.get("panelsJSON"))
    out: list[Panel] = []
    for p in raw:
        # inline (Serverless/new schema) panels carry type + config; classic panels carry embeddableConfig + panelRefName
        ptype = p.get("type", "")
        cfg = p.get("embeddableConfig") or p.get("config") or {}
        title = cfg.get("title") or (cfg.get("attributes") or {}).get("title") or p.get("title") or ptype
        attrs = cfg.get("attributes")
        sv = cfg.get("savedVis")
        if attrs is None and isinstance(sv, dict):  # by-value legacy visualization
            data = sv.get("data") or {}
            attrs = {"visState": json.dumps({"type": sv.get("type"), "params": sv.get("params") or {}, "aggs": data.get("aggs") or []}),
                     "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(data.get("searchSource") or {})}}
        prefs = (attrs or {}).get("references") or []
        ref_name = p.get("panelRefName")
        if ref_name and not attrs:
            rid = next((r["id"] for r in refs if r.get("name") in (ref_name, f"{p.get('panelIndex')}:{ref_name}")), None)
            rtype = next((r["type"] for r in refs if r.get("name") in (ref_name, f"{p.get('panelIndex')}:{ref_name}")), ptype)
            obj = resolver.objects.get((rtype, rid))
            if not obj:
                out.append(Panel(title, f"missing:{rtype}", checked=False))
                continue
            attrs, prefs, ptype = obj.get("attributes", {}), obj.get("references") or [], rtype
            title = cfg.get("title") or attrs.get("title") or title
        if attrs is None:
            out.append(Panel(title, ptype or "unknown", checked=False))
            continue
        # by-value panels keep their references on the dashboard with a "<panelIndex>:" prefix
        if not prefs:
            pi = str(p.get("panelIndex", ""))
            prefs = [{**r, "name": r["name"].split(":", 1)[1]} for r in refs if pi and r.get("name", "").startswith(pi + ":")]
        if "state" in attrs and "visState" not in attrs:
            out.append(resolver.lens(title, attrs, scope))
        elif ptype == "visualization" or "visState" in attrs:
            out.append(resolver.visualization(title, attrs, prefs, scope))
        elif ptype == "search" or "columns" in attrs:
            out.append(resolver.search(title, attrs, prefs, scope))
        elif ptype == "map" or "layerListJSON" in attrs:
            out.append(resolver.map(title, attrs, prefs, scope))
        else:
            out.append(Panel(title, ptype or "unknown", checked=False))
    return out


def _json_list(s: Any) -> list:
    v = _json(s) if not isinstance(s, list) else s
    if isinstance(v, list):
        return v
    try:
        r = json.loads(s)
        return r if isinstance(r, list) else []
    except (TypeError, ValueError):
        return []


# ---------- fetching ----------------------------------------------------------------------------------------------

def installed_dashboards(kb, only_packages: set[str] | None = None) -> list[dict]:
    st, body = kb("GET", "/api/fleet/epm/packages/installed?perPage=500")
    out = []
    for it in body.get("items", []) if st == 200 else []:
        name = it["name"]
        if only_packages is not None and name not in only_packages:
            continue
        st, info = kb("GET", f"/api/fleet/epm/packages/{name}/{it['version']}")
        info = info.get("item", info) if isinstance(info, dict) else {}
        for a in (info.get("installationInfo") or {}).get("installed_kibana") or []:
            if a.get("type") == "dashboard":
                out.append({"package": name, "version": it["version"], "id": a["id"]})
    return out


def bulk_get(kb, items: list[tuple[str, str]], chunk: int = 100) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    items = sorted(set(items))
    for i in range(0, len(items), chunk):
        st, body = kb("POST", "/api/saved_objects/_bulk_get", [{"type": t, "id": x} for t, x in items[i:i + chunk]])
        if st == 200:
            for o in body.get("saved_objects", []):
                if not o.get("error"):
                    out[(o["type"], o["id"])] = o
    return out


def load_dashboards(kb, only_packages: set[str] | None = None) -> list[dict]:
    """Return [{package, id, title, panels:[Panel]}] with every panel resolved."""
    dashes = installed_dashboards(kb, only_packages)
    objs = bulk_get(kb, [("dashboard", d["id"]) for d in dashes])
    wanted: list[tuple[str, str]] = []
    for o in objs.values():
        for r in o.get("references") or []:
            if r.get("type") in ("lens", "visualization", "search", "map", "index-pattern"):
                wanted.append((r["type"], r["id"]))
    level1 = bulk_get(kb, wanted)
    wanted2 = []  # index patterns and searches referenced by those objects
    for o in level1.values():
        for r in o.get("references") or []:
            if r.get("type") in ("index-pattern", "search"):
                wanted2.append((r["type"], r["id"]))
        if o["type"] == "map":
            for lyr in _json_list(o.get("attributes", {}).get("layerListJSON")):
                pid = (lyr.get("sourceDescriptor") or {}).get("indexPatternId")
                if pid:
                    wanted2.append(("index-pattern", pid))
    level2 = bulk_get(kb, [w for w in wanted2 if w not in level1])
    level3 = bulk_get(kb, [(r["type"], r["id"]) for o in level2.values() for r in o.get("references") or []
                           if r.get("type") == "index-pattern" and (r["type"], r["id"]) not in level1 and (r["type"], r["id"]) not in level2])
    resolver = Resolver({**objs, **level1, **level2, **level3})
    out = []
    for d in dashes:
        o = objs.get(("dashboard", d["id"]))
        if not o:
            continue
        out.append({**d, "title": o["attributes"].get("title", d["id"]), "panels": dashboard_panels(o, resolver)})
    return out


# ---------- evaluation --------------------------------------------------------------------------------------------

def _src_key(s: Source) -> str:
    return json.dumps([s.index, s.filters], sort_keys=True)


def _probe(es, index: str, filters: list[dict], fields: list[str], since: str) -> dict:
    """Doc count and per-field exists counts for one (index, filters) over a window."""
    body: dict[str, Any] = {"size": 0, "track_total_hits": True, "timeout": "20s",
                            "query": {"bool": {"filter": [{"range": {"@timestamp": {"gte": since}}}, *filters]}}}
    if fields:
        body["aggs"] = {f"f{i}": {"filter": {"exists": {"field": f}}} for i, f in enumerate(fields)}
    st, r = es("POST", f"/{index}/_search?ignore_unavailable=true&allow_no_indices=true", body)
    if st != 200:
        return {"error": str(r)[:200], "total": 0, "fields": {f: 0 for f in fields}}
    aggs = r.get("aggregations", {})
    return {"total": r["hits"]["total"]["value"], "fields": {f: aggs.get(f"f{i}", {}).get("doc_count", 0) for i, f in enumerate(fields)}}


def _probe_multi(es, index: str, filters: list[dict], fields: list[str], since: str) -> dict:
    out = {"total": 0, "fields": {}}
    first = True
    for i in range(0, max(len(fields), 1), 150):
        r = _probe(es, index, filters, fields[i:i + 150], since)
        if first:
            out["total"], first = r["total"], False
        out["fields"].update(r["fields"])
        if "error" in r:
            out["error"] = r["error"]
    return out


def _esql_has_rows(es, query: str, since: str) -> bool:
    body = {"query": query, "filter": {"range": {"@timestamp": {"gte": since}}}, "params": []}
    if "?_tstart" in query:
        body["params"].append({"_tstart": _iso_ago(since)})
    if "?_tend" in query:
        body["params"].append({"_tend": _iso_ago("now")})
    if not body["params"]:
        del body["params"]
    st, r = es("POST", "/_query", body)
    if st != 200 or not isinstance(r, dict):
        return False
    rows = r.get("values") or []
    if not rows:
        return False
    if len(rows) == 1 and all(v in (0, None) for v in rows[0]):
        return False
    return True


def _iso_ago(since: str) -> str:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    m = re.fullmatch(r"now-(\d+)([mhd])", since)
    if m:
        now -= timedelta(**{{"m": "minutes", "h": "hours", "d": "days"}[m.group(2)]: int(m.group(1))})
    return now.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def evaluate(es, dashboards: list[dict], workers: int = 8) -> list[dict]:
    """Probe every distinct source per window and score every dashboard."""
    tasks: dict[tuple[str, str], tuple[str, list[dict], set[str], str]] = {}  # (window, key) -> ...
    for d in dashboards:
        for p in d["panels"]:
            for s in p.sources:
                for w, since in WINDOWS.items():
                    k = (w, _src_key(s))
                    cur = tasks.get(k)
                    tasks[k] = (s.index, s.filters, (cur[2] if cur else set()) | s.fields, since)
    results: dict[tuple[str, str], dict] = {}
    esql_tasks = {(w, q): since for d in dashboards for p in d["panels"] for q in p.esql for w, since in WINDOWS.items()}
    esql_res: dict[tuple[str, str], bool] = {}

    def run_probe(item):
        k, (idx, filt, flds, since) = item
        return k, _probe_multi(es, idx, filt, sorted(flds), since)

    def run_esql(item):
        (w, q), since = item
        return (w, q), _esql_has_rows(es, q, since)

    with ThreadPoolExecutor(workers) as ex:
        for k, r in ex.map(run_probe, tasks.items()):
            results[k] = r
        for k, r in ex.map(run_esql, esql_tasks.items()):
            esql_res[k] = r

    report = []
    for d in dashboards:
        panels_out, missing = [], set()
        for p in d["panels"]:
            if not p.checked:
                panels_out.append({"title": p.title, "kind": p.kind, "checked": False})
                continue
            ok = {}
            for w in WINDOWS:
                good = True
                for s in p.sources:
                    r = results[(w, _src_key(s))]
                    if r["total"] == 0:
                        good = False
                        if w == "7d":
                            missing.add(f"{s.index}: no documents")
                    for f in s.fields:
                        if r["fields"].get(f, 0) == 0:
                            good = False
                            if w == "7d":
                                missing.add(f)
                for q in p.esql:
                    if not esql_res[(w, q)]:
                        good = False
                        if w == "7d":
                            missing.add("esql: no rows")
                ok[w] = good
            panels_out.append({"title": p.title, "kind": p.kind, "checked": True, "ok15m": ok["15m"], "ok7d": ok["7d"],
                               "indices": sorted({s.index for s in p.sources})})
        data = [p for p in panels_out if p["checked"]]
        n7, n15 = sum(p["ok7d"] for p in data), sum(p["ok15m"] for p in data)
        if not data:
            status = "NO_DATA"
        elif n7 == 0:
            status = "EMPTY"
        elif n7 < len(data):
            status = "PARTIAL"
        elif n15 == 0:
            status = "STALE"
        else:
            status = "FILLED"
        report.append({"package": d["package"], "id": d["id"], "title": d["title"], "status": status, "panels": len(data),
                       "filled_7d": n7, "filled_15m": n15, "unchecked": len(panels_out) - len(data),
                       "missing": sorted(missing)[:25], "panel_detail": panels_out})
    return report


def summarize(report: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def render(report: list[dict], verbose: bool = False) -> str:
    lines = [f"dashboards: {len(report)}  " + "  ".join(f"{k}={v}" for k, v in sorted(summarize(report).items()))]
    by_pkg: dict[str, list[dict]] = {}
    for r in report:
        by_pkg.setdefault(r["package"], []).append(r)
    for pkg in sorted(by_pkg):
        lines.append(f"[{pkg}]")
        for r in sorted(by_pkg[pkg], key=lambda x: x["title"]):
            lines.append(f"  {r['status']:8} {r['filled_7d']}/{r['panels']} (15m {r['filled_15m']})  {r['title']}")
            if verbose and r["missing"]:
                lines.append("           missing: " + ", ".join(r["missing"][:8]))
    return "\n".join(lines)
