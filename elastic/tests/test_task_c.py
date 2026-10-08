import json
import re
from pathlib import Path

from elastic.dashboards.build import adhoc_index, build_ndjson
from elastic.dashboards.panels import DASHBOARDS, OWASP_DASHBOARD, PANELS, QUALITY_DASHBOARD
from elastic.rules import owasp_detections, quality_alerts

DIR = Path(__file__).resolve().parents[1] / "dashboards"
TEMPLATE = json.loads((DIR / "template.lens-esql.json").read_text())
META = json.loads((DIR / "template.meta.json").read_text())
DASHES = ("—", "–")


def test_alert_ids_names_and_shape():
    rules = quality_alerts.all_rules()
    assert set(rules) == {"glassbox-unanswered-rate", "glassbox-negative-sentiment", "glassbox-low-faithfulness",
                          "glassbox-restricted-probing", "glassbox-off-topic", "glassbox-language-mismatch"}
    for rid, b in rules.items():
        assert rid.startswith("glassbox-") and b["name"].startswith("Glass Box: ")
        assert not any(d in json.dumps(b) for d in DASHES)
        assert b["rule_type_id"] == ".es-query" and b["schedule"] == {"interval": "5m"} and b["actions"] == []
        assert b["params"]["searchType"] == "esqlQuery" and b["params"]["timeWindowSize"] == 1
        q = b["params"]["esqlQuery"]["esql"]
        assert q.startswith("FROM logs-genai_response*") and "NOW() - 1 hour" in q


def test_alert_thresholds_and_override():
    q = {k: v["params"]["esqlQuery"]["esql"] for k, v in quality_alerts.all_rules().items()}
    assert "responses >= 5 AND unanswered_pct > 40.0" in q["glassbox-unanswered-rate"]
    assert 'quality.user_sentiment == "negative"' in q["glassbox-negative-sentiment"] and "hits >= 3" in q["glassbox-negative-sentiment"]
    assert "quality.low_faithfulness == true" in q["glassbox-low-faithfulness"] and "hits >= 2" in q["glassbox-low-faithfulness"]
    p = q["glassbox-restricted-probing"]
    assert "quality.answered == false AND quality.hidden_count > 0" in p and "top_hidden_score" not in p
    assert "BY persona = quality.persona" in p and "probes >= 3" in p
    assert quality_alerts.BY_ID["glassbox-restricted-probing"].name == "Glass Box: Restricted topic attempts"
    assert "quality.off_topic == true" in q["glassbox-off-topic"] and "hits >= 3" in q["glassbox-off-topic"]
    assert "quality.lang_mismatch == true" in q["glassbox-language-mismatch"] and "hits >= 2" in q["glassbox-language-mismatch"]
    low = quality_alerts.all_rules({"glassbox-off-topic": 1})["glassbox-off-topic"]["params"]["esqlQuery"]["esql"]
    assert "hits >= 1" in low and "hits >= 3" in q["glassbox-off-topic"]


def test_detection_rules():
    bodies = owasp_detections.rule_bodies()
    assert [b["rule_id"] for b in bodies] == ["glassbox-llm02-pii-in-response", "glassbox-llm05-unsafe-output",
                                              "glassbox-llm07-system-prompt-leak"]
    for b, reason, owasp in zip(bodies, ("pii_in_response", "unsafe_markup", "system_prompt_leak"),
                                ("LLM02", "LLM05", "LLM07")):
        assert b["query"] == f'output_reasons : "{reason}"' and b["index"] == ["logs-genai_response*"]
        assert b["interval"] == "1m" and b["from"] == "now-5m" and b["type"] == "query" and b["language"] == "kuery"
        assert f"OWASP {owasp}" in b["tags"] and owasp in b["description"] and "MITRE" in b["description"]
        assert b["name"].startswith("Glass Box: ") and not any(d in json.dumps(b) for d in DASHES)
        assert b["severity"] in {"medium", "high"}


def test_dashboard_registry_ids_titles_and_overview_unchanged():
    assert [d.id for d in DASHBOARDS] == ["glassbox-overview", "glassbox-quality", "glassbox-owasp"]
    assert QUALITY_DASHBOARD.title == "Glass Box: Conversation quality"
    assert OWASP_DASHBOARD.title == "Glass Box: OWASP LLM Top 10 coverage"
    assert len(DASHBOARDS[0].panels) == len(PANELS)
    for d in DASHBOARDS:
        line = build_ndjson(list(d.panels), TEMPLATE, META, d)
        obj = json.loads(line)
        assert obj["id"] == d.id and obj["attributes"]["title"] == d.title and obj["type"] == "dashboard"
        panels = json.loads(obj["attributes"]["panelsJSON"])
        assert len(panels) == len(d.panels) and len({p["panelIndex"] for p in panels}) == len(panels)
        assert not any(c in line for c in DASHES)
        assert "metrics-trader" not in line


def test_new_panels_query_typed_fields_and_are_bounded():
    for d in (QUALITY_DASHBOARD, OWASP_DASHBOARD):
        for p in d.panels:
            assert not any(c in p.title for c in DASHES), p.title
            assert p.chart == "table" or "STATS" in p.esql, p.title
            m = re.search(r"LIMIT (\d+)", p.esql)
            if m:
                assert int(m.group(1)) <= 100
            else:
                assert p.chart in ("metric", "table") or "BUCKET(" in p.esql, p.title
            if p.chart != "table":
                for col in (p.x, p.y, p.split, *p.extra_y):
                    if col:
                        assert re.search(rf"\b{col} = ", p.esql), (p.title, col)
    titles = [p.title for p in QUALITY_DASHBOARD.panels]
    assert "Top unanswered prompts" in titles
    top = next(p for p in QUALITY_DASHBOARD.panels if p.title == "Top unanswered prompts")
    assert "quality.answered == false" in top.esql and "quality.prompt_text" in top.esql and "LIMIT 10" in top.esql


def test_owasp_dashboard_covers_each_risk_and_marks_visibility_only():
    titles = " ".join(p.title for p in OWASP_DASHBOARD.panels)
    for risk in ("LLM01", "LLM02", "LLM05", "LLM07", "LLM08", "LLM09", "LLM10", "LLM03 and LLM06 visibility only"):
        assert risk in titles, risk
    spend = next(p for p in OWASP_DASHBOARD.panels if p.title.startswith("LLM10"))
    assert "NOW() - 24 hours" in spend.esql and "traces-generic.otel-default" in spend.esql
    table = next(p for p in OWASP_DASHBOARD.panels if p.chart == "table")
    assert table.esql.startswith("ROW") and adhoc_index(table.esql, table.index) == "traces-generic.otel-default"
    obj = json.loads(build_ndjson(list(OWASP_DASHBOARD.panels), TEMPLATE, META, OWASP_DASHBOARD))
    tp = json.loads(obj["attributes"]["panelsJSON"])[-1]["embeddableConfig"]["attributes"]
    assert tp["visualizationType"] == "lnsDatatable"
    assert [c["columnId"] for c in tp["state"]["visualization"]["columns"]] == list(table.cols)


def test_owasp_reason_panels_are_multivalue_safe_and_scope_column_is_not_constant():
    by = {p.title: p.esql for p in OWASP_DASHBOARD.panels}
    for t, r in (("LLM02 PII in responses", "pii_in_response"), ("LLM05 unsafe markup in responses", "unsafe_markup"),
                 ("LLM07 system prompt leaks", "system_prompt_leak")):
        assert f'MV_CONTAINS(output_reasons, "{r}")' in by[t] and "output_reasons ==" not in by[t]
    assert any("restricted topic attempts" in t for t in by)
    table = by["OWASP risk to Elastic control"]
    assert "visibility only" in table and "covered" not in table
    assert "LLM03|Supply chain|Visibility only" in table and "LLM06|Excessive agency|Visibility only" in table


def test_quality_dashboard_starts_with_two_full_width_list_tables():
    from elastic.dashboards.build import _layout
    first, second = QUALITY_DASHBOARD.panels[:2]
    assert (first.title, second.title) == ("Answered prompts, responses and flags", "Blocked and flagged prompts (guardrail)")
    assert first.chart == second.chart == "table" and first.wide and second.wide
    assert len(QUALITY_DASHBOARD.panels) == 12
    lay = _layout(list(QUALITY_DASHBOARD.panels))
    assert lay[0] == (0, 0, 48, 14) and lay[1] == (0, 14, 48, 14) and lay[2][1] == 28
    assert len({(x, y) for x, y, _, _ in lay}) == len(lay)
    q = first.esql
    assert q.startswith("FROM logs-genai_response* | SORT @timestamp DESC | LIMIT 100")
    for needle in ("quality.prompt_text AS prompt", "quality.response_text AS response", "EVAL flag = CASE(joined",
                   "output_reasons", "quality.off_topic", "quality.lang_mismatch", "quality.low_faithfulness",
                   'quality.user_sentiment == "negative"', "quality.answered == false"):
        assert needle in q, needle
    g = second.esql
    assert 'name == "guardrail.check"' in g and 'attributes.guardrail.verdict == "FLAGGED"' in g
    assert "attributes.guardrail.prompt_text AS prompt" in g and "trace.id AS trace_id" in g
    obj = json.loads(build_ndjson(list(QUALITY_DASHBOARD.panels), TEMPLATE, META, QUALITY_DASHBOARD))
    panels = json.loads(obj["attributes"]["panelsJSON"])
    for spec, panel in zip((first, second), panels[:2]):
        assert panel["gridData"]["w"] == 48 and panel["gridData"]["h"] == 14
        viz = panel["embeddableConfig"]["attributes"]["state"]["visualization"]
        assert panel["embeddableConfig"]["attributes"]["visualizationType"] == "lnsDatatable"
        assert [c["columnId"] for c in viz["columns"]] == list(spec.cols) and viz["rowHeight"] == "auto"
        assert {c["columnId"]: c["width"] for c in viz["columns"] if "width" in c} == dict(spec.widths)
