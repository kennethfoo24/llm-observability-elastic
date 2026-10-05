import json
from pathlib import Path

from elastic.dashboards.build import DASHBOARD_ID, adhoc_index, build_ndjson, dashboard_object
from elastic.dashboards.panels import PANELS

DIR = Path(__file__).resolve().parents[1] / "dashboards"
TEMPLATE = json.loads((DIR / "template.lens-esql.json").read_text())
META = json.loads((DIR / "template.meta.json").read_text())


def _dash(panels=PANELS):
    lines = [json.loads(line) for line in build_ndjson(panels, TEMPLATE, META).strip().splitlines()]
    assert len(lines) == 1
    return lines[0], json.loads(lines[0]["attributes"]["panelsJSON"])


def _assert_shape(p):
    import re
    # every plotted column is an alias produced by this query
    for col in (p.x, p.y, p.split, *p.extra_y):
        if col:
            assert re.search(rf"\b{col} = ", p.esql), (p.title, col)
    limit = re.search(r"LIMIT (\d+)", p.esql)
    if limit:
        assert int(limit.group(1)) <= 100, p.title
    else:  # unbounded cardinality is only acceptable for a single-row metric or a time bucket axis
        assert p.chart == "metric" or "BUCKET(" in p.esql, p.title
    assert "STATS" in p.esql and ("| LIMIT" not in p.esql or p.esql.index("STATS") < p.esql.index("LIMIT")), p.title


def test_every_panel_query_targets_this_service_and_has_a_bounded_limit():
    assert len(PANELS) >= 6
    for p in PANELS:
        assert 'service.name == "glassbox-backend"' in p.esql or "genai_guardrail" in p.esql, p.title
        _assert_shape(p)
        assert not any(ch in p.title for ch in ("—", "–"))
        assert "thinking_tokens" not in p.esql and "TO_DOUBLE" not in p.esql


def test_latency_panel_converts_nanoseconds_to_milliseconds_and_lists_real_span_names():
    lat = next(p for p in PANELS if "latency" in p.title.lower())
    for name in ("guardrail.check", "retrieval.hybrid", "prompt.build", "chat "):
        assert name in lat.esql
    assert "1000000" in lat.esql and "p95_ms" in lat.esql


def test_build_emits_one_valid_dashboard_object_with_one_by_value_panel_per_spec():
    obj, panels = _dash()
    assert obj["type"] == "dashboard" and obj["id"] == DASHBOARD_ID == "glassbox-overview"
    assert obj["attributes"]["title"] == "Glass Box: LLM observability"
    assert obj["references"] == [] and len(panels) == len(PANELS)
    assert [p["embeddableConfig"]["attributes"]["title"] for p in panels] == [p.title for p in PANELS]
    assert len({p["panelIndex"] for p in panels}) == len(PANELS)
    assert all(p["panelIndex"] == p["gridData"]["i"] and p["type"] == "lens" for p in panels)


def test_grid_is_two_per_row_without_overlap():
    _, panels = _dash()
    cells = {(p["gridData"]["x"], p["gridData"]["y"]) for p in panels}
    assert len(cells) == len(panels)
    assert {p["gridData"]["x"] for p in panels} <= {0, 24}
    assert all(p["gridData"]["w"] == 24 for p in panels)


def test_queries_and_columns_are_substituted_everywhere_the_template_repeats_them():
    _, panels = _dash()
    for spec, panel in zip(PANELS, panels):
        attrs = panel["embeddableConfig"]["attributes"]
        st = attrs["state"]
        layer = next(iter(st["datasourceStates"]["textBased"]["layers"].values()))
        assert layer["query"]["esql"] == spec.esql and st["query"]["esql"] == spec.esql
        assert "metrics-trader" not in json.dumps(panel) and "Shares" not in json.dumps(panel)
        cols = {c["columnId"] for c in layer["columns"]}
        assert {spec.x, spec.y} <= cols and ({spec.split} <= cols if spec.split else True)
        viz = st["visualization"]
        if spec.chart == "metric":
            assert viz["metricAccessor"] == spec.y
        else:
            lay = viz["layers"][0]
            assert lay["xAccessor"] == spec.x and lay["accessors"][0] == spec.y
            assert lay["splitAccessors"] == ([spec.split] if spec.split else [])
            assert lay["layerId"] in st["datasourceStates"]["textBased"]["layers"]


def test_ad_hoc_data_view_is_rebuilt_from_the_from_clause():
    _, panels = _dash()
    for spec, panel in zip(PANELS, panels):
        st = panel["embeddableConfig"]["attributes"]["state"]
        index = adhoc_index(spec.esql)
        assert index in ("traces-generic.otel-default", "logs-genai_guardrail*")
        (dv_id, dv), = st["adHocDataViews"].items()
        assert dv["title"] == index and dv["type"] == "esql" and dv["timeFieldName"] == "@timestamp" and dv["id"] == dv_id
        layer = next(iter(st["datasourceStates"]["textBased"]["layers"].values()))
        assert layer["index"] == dv_id and st["datasourceStates"]["textBased"]["indexPatternRefs"][0]["title"] == index
        assert all(c["meta"]["sourceParams"]["indexPattern"] == index for c in layer["columns"])


def test_chart_kinds_map_to_lens_visualisations():
    _, panels = _dash()
    for spec, panel in zip(PANELS, panels):
        attrs = panel["embeddableConfig"]["attributes"]
        if spec.chart == "metric":
            assert attrs["visualizationType"] == "lnsMetric"
        else:
            assert attrs["visualizationType"] == "lnsXY"
            assert attrs["state"]["visualization"]["layers"][0]["seriesType"] == (
                "line" if spec.chart == "line" else "bar")


def test_template_is_not_mutated_and_output_is_deterministic():
    before = json.dumps(TEMPLATE, sort_keys=True)
    a = build_ndjson(PANELS, TEMPLATE, META)
    assert json.dumps(TEMPLATE, sort_keys=True) == before
    assert a == build_ndjson(PANELS, TEMPLATE, META)


def test_dashboard_object_has_no_em_dash_and_is_default_time_range_aware():
    d = dashboard_object([])
    assert "—" not in json.dumps(d) and d["attributes"]["timeRestore"] is False


def test_dashboard_carries_migration_versions_or_kibana_import_returns_500():
    obj, _ = _dash()
    assert obj["coreMigrationVersion"] == "8.8.0" and obj["typeMigrationVersion"] == "10.3.0"
