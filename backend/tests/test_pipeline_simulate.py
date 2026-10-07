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


GUARD_FIELDS = ("threat_verdict", "threat_reasons", "models_ok", "injection_score", "person_count")


def _guard_field(src: dict, name: str):
    """Read a guard output from nested (attributes.security.x) or flat-dotted (attributes['security.x']) layout."""
    root, rest = GUARD_PREFIX.split(".", 1)
    try:
        return _nested(src, f"{GUARD_PREFIX}.{name}")
    except (KeyError, TypeError):
        return src[root][f"{rest}.{name}"]


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
    assert _guard_field(src, "threat_verdict") == case["expected_verdict"]
    reasons = _guard_field(src, "threat_reasons") if case["expected_reasons"] else []
    assert sorted(reasons) == sorted(case["expected_reasons"])
    assert "guard_tmp" not in src
    assert _guard_field(src, "models_ok") is True
    if case["expected_verdict"] == "CLEAN":
        assert _guard_field(src, "threat_reasons") == []
    label, prob = case["injection"]["label"], case["injection"]["score"]
    p_inj = prob if label == "INJECTION" else 1 - prob
    assert isinstance(_guard_field(src, "injection_score"), float)
    assert _guard_field(src, "injection_score") == pytest.approx(p_inj)


_OK_MODELS = {"injection": {"predicted_value": "SAFE", "prediction_probability": 0.01}, "ner": {"entities": []}}


def _run(doc: dict) -> dict:
    s = Settings()
    es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
    out = es.ingest.simulate(pipeline=build_pipeline(include_inference=False), docs=[{"_source": doc}])["docs"][0]
    assert "error" not in out, out
    src = out["doc"]["_source"]
    assert "guard_tmp" not in src
    return {name: _guard_field(src, name) for name in GUARD_FIELDS}


@pytest.mark.integration
@pytest.mark.parametrize("label,prob,expected", [("SAFE", 0.99999, 1e-5), ("INJECTION", 0.99, 0.99)])
def test_injection_score_is_p_injection(label, prob, expected):
    g = _run({"attributes": {"genai": {"prompt_text": "hello"}},
              "guard_tmp": {"injection": {"predicted_value": label, "prediction_probability": prob},
                            "ner": {"entities": []}}})
    assert isinstance(g["injection_score"], float)
    assert g["injection_score"] == pytest.approx(expected, abs=1e-9)
    assert isinstance(g["person_count"], int) and g["person_count"] == 0


@pytest.mark.integration
def test_injection_score_is_zero_when_injection_prediction_is_absent():
    g = _run({"attributes": {"genai": {"prompt_text": "hello"}}, "guard_tmp": {"ner": {"entities": []}}})
    assert g["injection_score"] == 0.0


@pytest.mark.integration
def test_script_failure_falls_back_to_flat_unknown_verdict():
    s = Settings()
    es = Elasticsearch(s.obs_es_url, api_key=s.obs_es_admin_key)
    doc = {"attributes": {"genai": {"prompt_text": "hello"}},
           "guard_tmp": {"injection": {"predicted_value": ["not", "a", "string"],
                                       "prediction_probability": 0.5}, "ner": {"entities": []}}}
    out = es.ingest.simulate(pipeline=build_pipeline(include_inference=False), docs=[{"_source": doc}])["docs"][0]
    src = out["doc"]["_source"]
    assert "guard_tmp" not in src and _guard_field(src, "threat_verdict") == "UNKNOWN"


@pytest.mark.integration
def test_flat_dotted_attribute_key_is_expanded():
    g = _run({"attributes": {"genai.prompt_text": "email alex.tan@foo-corp.example"},
              "guard_tmp": dict(_OK_MODELS)})
    assert g["threat_verdict"] == "FLAGGED" and g["threat_reasons"] == ["pii_email"]


@pytest.mark.integration
def test_missing_prompt_field_is_unknown_without_error():
    g = _run({"message": "no prompt here"})
    assert g["threat_verdict"] == "UNKNOWN"


@pytest.mark.integration
def test_multi_pii_all_reasons():
    prompt = "Mail a@b.example, NRIC S1234567D, call +65 9123 4567, pay 127,500"
    g = _run({"attributes": {"genai": {"prompt_text": prompt}}, "guard_tmp": dict(_OK_MODELS)})
    assert g["threat_verdict"] == "FLAGGED"
    assert sorted(g["threat_reasons"]) == ["pii_email", "pii_nric", "pii_phone", "pii_salary"]


@pytest.mark.integration
def test_model_outage_is_unknown_not_clean_but_pii_still_flags():
    clean = _run({"attributes": {"genai": {"prompt_text": "How many PTO days do I get?"}}})
    assert clean["threat_verdict"] == "UNKNOWN" and clean["models_ok"] is False
    pii = _run({"attributes": {"genai": {"prompt_text": "email alex.tan@foo-corp.example"}}})
    assert pii["threat_verdict"] == "FLAGGED" and pii["threat_reasons"] == ["pii_email"]
    assert pii["models_ok"] is False


def test_hook_preserves_existing_processors_and_is_idempotent():
    existing = {"processors": [{"set": {"field": "x", "value": 1}}]}
    once = build_hook(existing)
    twice = build_hook(once)
    assert once["processors"][0] == {"set": {"field": "x", "value": 1}}
    assert len(twice["processors"]) == len(once["processors"]) == 2
    assert once["processors"][1]["pipeline"]["name"] == "genai-guardrail"
