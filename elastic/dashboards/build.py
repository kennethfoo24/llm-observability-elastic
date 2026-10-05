"""Build the Glass Box dashboard as ONE dashboard saved object with by-value Lens panels.

Serverless Kibana stores Lens panels inline in the dashboard (no separate `lens` saved objects), so each
panel is a clone of the extracted template (template.lens-esql.json, RFC 6901 pointers in template.meta.json)
with title, ES|QL, columns, accessors and the ad hoc data view rebuilt for the panel's own FROM index.
"""
import copy
import hashlib
import json
import re
import uuid

from .panels import Panel

DASHBOARD_ID = "glassbox-overview"
DASHBOARD_TITLE = "Glass Box: LLM observability"
TIME_FIELD = "@timestamp"
_FROM = re.compile(r"^\s*(?:FROM|TS)\s+([^\s|,]+)", re.IGNORECASE)


def _walk(obj, parts: list[str]):
    for part in parts:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def _parts(pointer: str) -> list[str]:
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer.lstrip("/").split("/")]


def _set(obj: dict, pointer: str, value) -> None:
    parts = _parts(pointer)
    parent, last = _walk(obj, parts[:-1]), parts[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    else:
        parent[last] = value


def adhoc_index(esql: str) -> str:
    m = _FROM.match(esql)
    if not m:
        raise ValueError(f"cannot find the FROM index in: {esql[:60]}")
    return m.group(1)


def _data_view_id(index: str) -> str:
    return hashlib.sha256(index.encode()).hexdigest()


def _column(name: str, kind: str, index: str) -> dict:
    es_type = {"date": "date", "number": "double", "string": "keyword"}[kind]
    col = {"columnId": name, "fieldName": name, "label": name, "customLabel": False,
           "meta": {"type": kind, "esType": es_type,
                    "sourceParams": {"params": {}, "indexPattern": index, "sourceField": name},
                    "params": {"id": kind}}}
    if kind == "number":
        col["inMetricDimension"] = True
    return col


def _columns(p: Panel, index: str) -> list[dict]:
    if p.chart == "metric":
        return [_column(p.y, "number", index)]
    cols = [_column(p.y, "number", index), *[_column(y, "number", index) for y in p.extra_y]]
    cols.append(_column(p.x, "date" if p.chart == "line" else "string", index))
    if p.split:
        cols.append(_column(p.split, "string", index))
    return cols


def _panel(i: int, p: Panel, template: dict, meta: dict) -> dict:
    ptr = meta["pointers"] if "pointers" in meta else meta
    obj = copy.deepcopy(template)
    index = adhoc_index(p.esql)
    dv_id = _data_view_id(index)
    _set(obj, ptr["panel_title"], p.title)
    _set(obj, ptr["esql_string"], p.esql)
    _set(obj, ptr["esql_string_state_query"], p.esql)

    layer_parts = _parts(ptr["datasource_columns"])[:-1]
    layer = _walk(obj, layer_parts)
    layer["columns"] = _columns(p, index)
    layer["index"] = dv_id
    layer["timeField"] = TIME_FIELD

    state = obj["embeddableConfig"]["attributes"]["state"]
    state["datasourceStates"]["textBased"]["indexPatternRefs"] = [
        {"id": dv_id, "title": index, "timeField": TIME_FIELD}]
    view = next(iter(state["adHocDataViews"].values()))
    view.update({"id": dv_id, "title": index, "name": index, "timeFieldName": TIME_FIELD})
    state["adHocDataViews"] = {dv_id: view}

    attrs = obj["embeddableConfig"]["attributes"]
    layer_id = _walk(obj, _parts(ptr["layer_id"]))
    if p.chart == "metric":
        attrs["visualizationType"] = "lnsMetric"
        state["visualization"] = {"layerId": layer_id, "layerType": "data", "metricAccessor": p.y}
    else:
        _set(obj, ptr["x_column"], p.x)
        _set(obj, ptr["y_column"], p.y)
        _set(obj, ptr["series_type"], "line" if p.chart == "line" else "bar")
        lay = state["visualization"]["layers"][0]
        lay["accessors"] = [p.y, *p.extra_y]
        lay["splitAccessors"] = [p.split] if p.split else []
        state["visualization"]["preferredSeriesType"] = "line" if p.chart == "line" else "bar"
        if not p.split:
            lay.pop("colorMapping", None)

    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"glassbox-panel-{i}-{p.title}"))
    grid = dict(_walk(obj, _parts(ptr["grid"])))
    grid.update({"x": (i % 2) * 24, "y": (i // 2) * 15, "w": 24, "h": 15, "i": pid})
    obj["panelIndex"], obj["gridData"] = pid, grid
    return obj


def dashboard_object(panels_json: list[dict]) -> dict:
    return {
        "type": "dashboard", "id": DASHBOARD_ID,
        "attributes": {
            "title": DASHBOARD_TITLE,
            "description": "Cost, tokens, guardrails and latency for the Nimbus HR assistant.",
            "timeRestore": False,
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []})},
            "panelsJSON": json.dumps(panels_json),
            "optionsJSON": json.dumps({"useMargins": True, "syncColors": False, "syncCursor": True,
                                       "syncTooltips": False, "hidePanelTitles": False}),
        },
        "references": [],
        # Without these versions the import runs every migration on the by-value panels and returns HTTP 500.
        "coreMigrationVersion": "8.8.0", "typeMigrationVersion": "10.3.0",
    }


def build_ndjson(panels: list[Panel], template: dict, meta: dict) -> str:
    built = [_panel(i, p, template, meta) for i, p in enumerate(panels)]
    return json.dumps(dashboard_object(built)) + "\n"
