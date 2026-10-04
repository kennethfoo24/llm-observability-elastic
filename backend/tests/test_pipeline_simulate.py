import json
from pathlib import Path

import pytest
from elasticsearch import Elasticsearch

from app.config import Settings
from app.guardrail_pipeline import GUARD_PREFIX, PROMPT_FIELD, build_hook, build_pipeline

CASES = json.loads((Path(__file__).parent / "data" / "guardrail_cases.json").read_text())


def _nested(doc: dict, dotted: str):
    cur = doc
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def _set(doc: dict, dotted: str, value):
    cur = doc
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_pipeline_verdict_matches_shared_cases(case):
    s = Settings()
    es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
    doc: dict = {}
    _set(doc, PROMPT_FIELD, case["prompt"])
    doc["guard_tmp"] = {
        "injection": {"predicted_value": case["injection"]["label"],
                      "prediction_probability": case["injection"]["score"]},
        "ner": {"entities": case["entities"]},
    }
    pipeline = build_pipeline(include_inference=False)
    out = es.ingest.simulate(pipeline=pipeline, docs=[{"_source": doc}])["docs"][0]
    assert "error" not in out, out
    src = out["doc"]["_source"]
    assert _nested(src, f"{GUARD_PREFIX}.threat_verdict") == case["expected_verdict"]
    reasons = _nested(src, f"{GUARD_PREFIX}.threat_reasons") if case["expected_reasons"] else []
    assert sorted(reasons) == sorted(case["expected_reasons"])
    assert "guard_tmp" not in src


def test_hook_preserves_existing_processors_and_is_idempotent():
    existing = {"processors": [{"set": {"field": "x", "value": 1}}]}
    once = build_hook(existing)
    twice = build_hook(once)
    assert once["processors"][0] == {"set": {"field": "x", "value": 1}}
    assert len(twice["processors"]) == len(once["processors"]) == 2
    assert once["processors"][1]["pipeline"]["name"] == "genai-guardrail"
