import importlib.util
import json
from pathlib import Path

import pytest
from app.doc_scan_pipeline import (
    CHUNK_SIZE, INJECTION_THRESHOLD, MAX_CHUNKS, PATTERN_SCRIPT, PIPELINE_ID, STAGING_INDEX, VERDICT_SCRIPT,
    build_doc_scan_pipeline, index_body)
from app.guardrail_pipeline import INJECTION_MODEL
from app.index_def import INDEX_BODY

from elastic.client import Project
from elastic.dashboards.panels import OWASP_PANELS
from elastic.rules import doc_integrity

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("poison_demo", ROOT / "scripts" / "poison_demo.py")
poison_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poison_demo)


def _procs():
    return build_doc_scan_pipeline()["processors"]


def test_pipeline_fingerprints_title_content_classification_and_roles():
    fp = _procs()[0]["fingerprint"]
    assert fp["fields"] == ["title", "content", "classification", "allowed_roles"]
    assert fp["target_field"] == "doc_scan.fingerprint" and fp["method"] == "SHA-256"


def test_baseline_is_set_once():
    b = _procs()[1]["set"]
    assert b["field"] == "doc_scan.baseline_fingerprint" and b["copy_from"] == "doc_scan.fingerprint"
    assert b["override"] is False


def test_one_ignore_failure_inference_step_per_chunk():
    inf = [p["inference"] for p in _procs() if "inference" in p]
    assert len(inf) == MAX_CHUNKS == 4 and CHUNK_SIZE == 2000
    for i, p in enumerate(inf):
        assert p["model_id"] == INJECTION_MODEL and p["ignore_failure"] is True
        assert p["field_map"] == {f"doc_scan_tmp.c{i}": "text_field"} and f"c{i} != null" in p["if"]


def test_on_failure_sets_unknown_and_temp_is_removed():
    pl = build_doc_scan_pipeline()
    assert {"set": {"field": "doc_scan.verdict", "value": "UNKNOWN"}} in pl["on_failure"]
    assert any("remove" in p and p["remove"]["field"] == "doc_scan_tmp" for p in pl["processors"])


def test_pattern_script_covers_the_required_phrases():
    for needle in ("ignore_previous", "disregard_above", "system_prompt", "you_must_now", "reveal", "script_tag",
                   "hidden_unicode", "0xDB40", "0x200B", "credential_exfiltration"):
        assert needle in PATTERN_SCRIPT, needle


def test_verdict_script_text():
    for needle in ("'FLAGGED'", "'CLEAN'", "'UNKNOWN'", "prompt_injection", "instruction_patterns", "content_changed",
                   "params.injection_threshold", "d.injection_score", "baseline_fingerprint"):
        assert needle in VERDICT_SCRIPT, needle
    verdict = [p["script"] for p in _procs() if "script" in p and p["script"]["source"] == VERDICT_SCRIPT][0]
    assert verdict["params"]["injection_threshold"] == INJECTION_THRESHOLD == 0.85


def test_staging_mapping_is_hr_kb_plus_typed_result_fields():
    props = index_body()["mappings"]["properties"]
    for k, v in INDEX_BODY["mappings"]["properties"].items():
        assert props[k] == v
    ds = props["doc_scan"]["properties"]
    assert ds["verdict"] == {"type": "keyword"} and ds["injection_score"]["type"] == "double"
    assert ds["fingerprint"]["type"] == "keyword" and ds["baseline_fingerprint"]["type"] == "keyword"
    assert ds["scanned_at"]["type"] == "date" and props["@timestamp"]["type"] == "date"


def test_rule_is_a_5m_esql_rule_on_staging_only():
    b = doc_integrity.rule_body()
    q = b["params"]["esqlQuery"]["esql"]
    assert doc_integrity.RULE_ID == "glassbox-doc-integrity" and b["name"] == "Glass Box: Document scan flagged or changed"
    assert b["schedule"]["interval"] == "5m" and b["params"]["searchType"] == "esqlQuery"
    assert q.startswith("FROM hr-kb-staging ") and "hr-kb " not in q.replace("hr-kb-staging", "")
    assert 'doc_scan.verdict == "FLAGGED"' in q and "doc_scan.fingerprint != doc_scan.baseline_fingerprint" in q
    assert "doc_scan.scanned_at > NOW() - 24 hours" in q and "WHERE docs >= 1" in q


def test_owasp_dashboard_has_the_llm04_panel():
    p = [x for x in OWASP_PANELS if x.title == "Documents flagged or changed (LLM04)"]
    assert len(p) == 1 and p[0].esql.startswith("FROM hr-kb-staging")


def test_demo_documents_and_ids():
    docs = poison_demo.build_documents()
    assert [d[0] for d in docs] == ["clean", "clean", "poisoned", "tampered"]
    assert docs[3][1] == docs[0][1] and docs[3][2]["content"] != docs[0][2]["content"]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in docs[2][2]["content"]
    assert all(i.startswith("demo-") for i in poison_demo.demo_ids())
    assert poison_demo.STAGING_INDEX == STAGING_INDEX == "hr-kb-staging" and PIPELINE_ID == "genai-doc-scan"


@pytest.mark.integration
def test_simulate_clean_and_poisoned_document():
    p = Project("observability")
    docs = [{"_source": s} for _, _, s in poison_demo.build_documents()[:3]]
    status, body = p.es("POST", f"/_ingest/pipeline/_simulate", {"pipeline": build_doc_scan_pipeline(), "docs": docs})
    assert status == 200, str(body)[:300]
    clean, _, poisoned = [d["doc"]["_source"]["doc_scan"] for d in body["docs"]]
    assert clean["verdict"] == "CLEAN" and clean["changed"] is False and clean["patterns"] == []
    assert poisoned["verdict"] == "FLAGGED" and "prompt_injection" in poisoned["reasons"]
    assert "ignore_previous" in poisoned["patterns"]
    assert clean["fingerprint"] == clean["baseline_fingerprint"] and len(clean["fingerprint"]) > 20
    assert "doc_scan_tmp" not in body["docs"][0]["doc"]["_source"]


@pytest.mark.integration
def test_simulate_tampered_and_hidden_unicode():
    p = Project("observability")
    src = dict(poison_demo.build_documents()[0][2])
    tampered = {**src, "content": src["content"] + " extra", "doc_scan": {"baseline_fingerprint": "trusted"}}
    hidden = {**src, "content": src["content"] + "​"}
    status, body = p.es("POST", "/_ingest/pipeline/_simulate",
                        {"pipeline": build_doc_scan_pipeline(), "docs": [{"_source": tampered}, {"_source": hidden}]})
    assert status == 200, str(body)[:300]
    t, h = [d["doc"]["_source"]["doc_scan"] for d in body["docs"]]
    assert t["changed"] is True and t["baseline_fingerprint"] == "trusted" and t["verdict"] == "CLEAN"
    assert h["verdict"] == "FLAGGED" and h["patterns"] == ["hidden_unicode"]
