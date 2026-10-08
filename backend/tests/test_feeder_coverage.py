import json

from feeder import coverage


def lens_panel(fields, ref="logs-*", extra_state=None):
    layer = {"columns": {f"c{i}": {"sourceField": f, "operationType": "sum"} for i, f in enumerate(fields)}}
    return {"type": "lens", "panelIndex": "p1", "embeddableConfig": {"attributes": {
        "title": "t", "references": [{"id": ref, "name": "indexpattern-datasource-layer-L1", "type": "index-pattern"}],
        "state": {"datasourceStates": {"formBased": {"layers": {"L1": layer}}}, "filters": [], "query": {"query": "", "language": "kuery"}, **(extra_state or {})}}}}


DASH = {"id": "d1", "attributes": {
    "title": "Fixture", "panelsJSON": json.dumps([
        lens_panel(["a.b", "___records___", "c.d"]),
        {"type": "lens", "panelIndex": "p2", "embeddableConfig": {"attributes": {"state": {
            "datasourceStates": {"textBased": {"layers": {"x": {"query": {"esql": "FROM metrics-x-* | LIMIT 1"}}}}}}, "references": []}}},
        {"type": "markdown", "panelIndex": "p3", "embeddableConfig": {}},
    ]),
    "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({"query": {"language": "kuery", "query": "x:1"},
        "filter": [{"meta": {"key": "event.action", "params": {"query": "go"}}, "query": {"match_phrase": {"event.action": "go"}}},
                   {"meta": {"disabled": True}, "query": {"match_all": {}}},
                   {"meta": {"negate": True, "key": "k", "params": {"query": "v"}}}]})}}, "references": []}


def test_lens_field_extraction_and_scope_from_fixture():
    panels = coverage.dashboard_panels(DASH, coverage.Resolver({}))
    assert len(panels) == 3
    p = panels[0]
    assert p.kind == "lens" and p.sources[0].index == "logs-*"
    assert p.sources[0].fields == {"a.b", "c.d"}  # ___records___ ignored
    scope = p.sources[0].filters
    assert {"match_phrase": {"event.action": "go"}} in scope and {"kql": {"query": "x:1"}} in scope
    assert {"bool": {"must_not": [{"match_phrase": {"k": "v"}}]}} in scope  # negated phrase built from meta
    assert len(scope) == 3  # the disabled filter is dropped
    assert panels[1].esql == ["FROM metrics-x-* | LIMIT 1"] and panels[1].checked
    assert not panels[2].checked  # markdown is static


def test_adhoc_data_view_and_runtime_fields_are_handled():
    attrs = {"references": [], "state": {"adHocDataViews": {"adhoc1": {"title": "metrics-*", "runtimeFieldMap": {"rt": {}}}},
                                         "datasourceStates": {"formBased": {"layers": {"L": {"columns": {"c": {"sourceField": "f1"}, "d": {"sourceField": "rt"}}}}}},
                                         "internalReferences": [{"id": "adhoc1", "name": "indexpattern-datasource-layer-L", "type": "index-pattern"}]}}
    p = coverage.Resolver({}).lens("t", attrs, [])
    assert p.sources[0].index == "metrics-*" and p.sources[0].fields == {"f1"}


def test_status_logic_empty_partial_stale_filled(monkeypatch):
    def mk(panels):
        return [{"package": "p", "id": "i", "title": "T", "panels": panels}]
    src = lambda f: coverage.Source("logs-*", {f}, [])
    ok, bad = coverage.Panel("ok", "lens", [src("have")]), coverage.Panel("bad", "lens", [src("missing")])

    def fake_probe(es, index, filters, fields, since):
        recent = since == coverage.WINDOWS["15m"]
        return {"total": 5, "fields": {f: (1 if f == "have" and (not recent or fake_probe.fresh) else 0) for f in fields}}
    monkeypatch.setattr(coverage, "_probe_multi", fake_probe)
    fake_probe.fresh = True
    assert coverage.evaluate(None, mk([ok, ok]))[0]["status"] == "FILLED"
    assert coverage.evaluate(None, mk([ok, bad]))[0]["status"] == "PARTIAL"
    assert coverage.evaluate(None, mk([bad]))[0]["status"] == "EMPTY"
    fake_probe.fresh = False
    assert coverage.evaluate(None, mk([ok]))[0]["status"] == "STALE"
    assert coverage.evaluate(None, mk([coverage.Panel("md", "markdown", checked=False)]))[0]["status"] == "NO_DATA"
    rep = coverage.evaluate(None, mk([ok, bad]))
    assert rep[0]["missing"] == ["missing"] and coverage.summarize(rep) == {"PARTIAL": 1}
    assert "PARTIAL" in coverage.render(rep, verbose=True)
