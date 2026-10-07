import json

import httpx
import pytest
from app.quality_pipeline import (
    FIELD_MAPPINGS, JUDGE_MODEL, PIPELINE_ID, QUALITY_HOOK_CONDITION, build_quality_hook, build_quality_pipeline)

from elastic import apply as apply_mod
from elastic.apply import apply_project, read_canary
from elastic.templates import COMPONENT_NAME, INDEX_PATTERN, build_component, build_index_template
from elastic.tests.test_apply import DEFAULT_TEMPLATE, _project

FAKE_CANARY = "GBX-0123456789abcdef"


def _models(pipeline):
    return [p["inference"].get("model_id") for p in pipeline["processors"] if "inference" in p]


def test_observability_pipeline_has_sentiment_topic_and_judge():
    ids = _models(build_quality_pipeline("observability"))
    assert "distilbert-base-uncased-finetuned-sst-2-english" in ids
    assert "typeform__distilbert-base-uncased-mnli" in ids
    assert JUDGE_MODEL in ids and "lang_ident_model_1" in ids
    zs = next(p["inference"] for p in build_quality_pipeline("observability")["processors"]
              if p.get("inference", {}).get("model_id") == "typeform__distilbert-base-uncased-mnli")
    assert "off topic" in zs["inference_config"]["zero_shot_classification"]["labels"]


def test_security_pipeline_is_the_subset_without_sentiment_topic_or_judge():
    pl = build_quality_pipeline("security")
    ids = _models(pl)
    assert ids == ["lang_ident_model_1", "lang_ident_model_1", "elastic__distilbert-base-cased-finetuned-conll03-english"]
    assert not any("json" in p for p in pl["processors"])
    assert not any("t.judge_input =" in p.get("script", {}).get("source", "") for p in pl["processors"])


def test_every_inference_step_ignores_failure_and_on_failure_sets_unknown():
    for proj in ("observability", "security"):
        pl = build_quality_pipeline(proj)
        assert all(p["inference"]["ignore_failure"] for p in pl["processors"] if "inference" in p)
        assert pl["on_failure"][0]["set"] == {"field": "output_verdict", "value": "UNKNOWN"}


def test_unknown_project_rejected():
    with pytest.raises(ValueError):
        build_quality_pipeline("search")


def test_painless_scripts_smoke():
    src = json.dumps(build_quality_pipeline("observability"))
    for needle in ("<script", "<iframe", "javascript:", "data:text/html", "on(?:error|load)", "system_prompt_leak",
                   "unsafe_markup", "pii_in_response", "'UNKNOWN'", "low_faithfulness", "lang_mismatch"):
        assert needle in src, needle
    assert "output_verdict" in src and "ctx.remove('quality_tmp')" in src


def test_canary_is_a_script_param_only_and_not_in_source():
    pl = build_quality_pipeline("security", FAKE_CANARY)
    checks = next(p["script"] for p in pl["processors"] if "canary" in p.get("script", {}).get("params", {}))
    assert checks["params"]["canary"] == FAKE_CANARY and FAKE_CANARY not in checks["source"]
    empty = next(p["script"] for p in build_quality_pipeline("security")["processors"]
                 if "canary" in p.get("script", {}).get("params", {}))
    assert empty["params"]["canary"] == ""


def test_hook_merge_idempotent_and_keeps_existing():
    base = {"processors": [{"set": {"field": "x", "value": 1}}]}
    once = build_quality_hook(base)
    assert once["processors"][0] == base["processors"][0] and len(once["processors"]) == 2
    assert build_quality_hook(once) == once
    hook = once["processors"][1]["pipeline"]
    assert hook["name"] == PIPELINE_ID and hook["if"] == QUALITY_HOOK_CONDITION and hook["ignore_failure"]
    assert "genai_response.otel" in QUALITY_HOOK_CONDITION


def test_templates_compose_default_components_then_ours():
    t = build_index_template(DEFAULT_TEMPLATE["index_templates"][0]["index_template"])
    assert t["composed_of"] == ["logs@mappings", "otel@mappings", "ecs@mappings", COMPONENT_NAME]
    assert t["index_patterns"] == [INDEX_PATTERN] and t["priority"] > 120 and t["data_stream"] == {}
    assert t["ignore_missing_component_templates"] == ["logs@custom"]
    assert build_component()["template"]["mappings"]["properties"] is FIELD_MAPPINGS
    q = FIELD_MAPPINGS["quality"]["properties"]
    assert q["faithfulness"]["type"] == "integer" and q["off_topic"]["type"] == "boolean"
    assert FIELD_MAPPINGS["output_verdict"]["type"] == "keyword"


def test_apply_puts_templates_pipelines_and_merged_hook_without_printing_canary(tmp_path, monkeypatch, capsys):
    cf = tmp_path / "canary.txt"
    cf.write_text(FAKE_CANARY + "\n")
    monkeypatch.setattr(apply_mod, "CANARY_FILE", cf)
    monkeypatch.setattr(apply_mod, "read_canary", lambda path=cf: read_canary(path))
    puts = {}

    def handler(req):
        if req.method == "PUT":
            puts[req.url.path] = json.loads(req.content)
        if req.method == "GET" and "logs@custom" in req.url.path:
            return httpx.Response(404, json={})
        return httpx.Response(200, json={"acknowledged": True, "success": True})

    for dry in (True, False):
        apply_project(_project(handler, "security"), cost_threshold=0.25, dry_run=dry)
    out = capsys.readouterr()
    assert FAKE_CANARY not in out.out + out.err and "canary set" in out.out
    assert f"/_component_template/{COMPONENT_NAME}" in puts and "/_index_template/glassbox-genai-response" in puts
    sent = puts["/_ingest/pipeline/genai-quality"]
    assert FAKE_CANARY in json.dumps(sent)           # installed into the cluster pipeline only
    assert not any("inference" in p and p["inference"]["model_id"] != "lang_ident_model_1"
                   and "conll03" not in p["inference"]["model_id"] for p in sent["processors"])
    assert len(puts["/_ingest/pipeline/logs@custom"]["processors"]) == 2


def test_missing_canary_file_reads_as_empty(tmp_path):
    assert read_canary(tmp_path / "none") == ""


def test_only_quality_touches_nothing_but_quality_objects():
    writes = []

    def handler(req):
        if req.method != "GET":
            writes.append(req.url.path)
        if req.method == "GET" and "logs@custom" in req.url.path:
            return httpx.Response(404, json={})
        return httpx.Response(200, json={"acknowledged": True})

    apply_project(_project(handler), 0.25, False, only_quality=True)
    assert sorted(writes) == sorted(["/_component_template/glassbox-genai-response@mappings",
                                     "/_index_template/glassbox-genai-response",
                                     "/_ingest/pipeline/genai-quality", "/_ingest/pipeline/logs@custom"])
