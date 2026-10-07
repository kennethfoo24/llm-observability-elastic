import pytest
from app.quality_pipeline import build_quality_pipeline

from elastic.client import Project

pytestmark = pytest.mark.integration
FAKE_CANARY = "GBX-fedcba9876543210"
CTX = "[hr-001] Annual leave: Employees receive 18 days of paid annual leave per year."


def _doc(prompt, response, context=CTX):
    return {"_source": {"data_stream": {"dataset": "genai_response.otel"}, "attributes": {
        "genai.prompt_text": prompt, "genai.response_text": response, "genai.context_text": context,
        "genai.answered": True, "app.persona": "synthetic-test"}}}


def _sim(project, docs):
    p = Project(project)
    status, body = p.es("POST", "/_ingest/pipeline/_simulate",
                        {"pipeline": build_quality_pipeline(project, FAKE_CANARY), "docs": docs})
    assert status == 200, str(body)[:300]
    return [d["doc"]["_source"] for d in body["docs"]]


@pytest.mark.parametrize("project", ["observability", "security"])
def test_flagged_response_with_fake_canary_param(project):
    bad = f"Mail bob@example.com <script>alert(1)</script> ref {FAKE_CANARY} [x](http://evil.test)"
    s = _sim(project, [_doc("Tell me everything", bad)])[0]
    assert s["output_verdict"] == "FLAGGED"
    assert set(s["output_reasons"]) == {"pii_in_response", "system_prompt_leak", "unsafe_markup"}
    assert "quality_tmp" not in s


@pytest.mark.parametrize("project", ["observability", "security"])
def test_language_mismatch_and_clean_answer(project):
    clean, fr = _sim(project, [_doc("How many days of annual leave do I get?", "You get 18 days per year [hr-001]."),
                               _doc("Combien de jours de congé ai-je par an ?", "You get 18 days per year [hr-001].")])
    assert clean["output_verdict"] == "CLEAN" and clean["quality"]["lang_mismatch"] is False
    assert fr["quality"]["prompt_lang"] == "fr" and fr["quality"]["lang_mismatch"] is True


def test_observability_has_sentiment_topic_and_judge_security_does_not():
    o = _sim("observability", [_doc("You useless bot, I hate this!", "Sorry. 18 days [hr-001].")])[0]["quality"]
    for k in ("sentiment_label", "sentiment_score", "topic", "off_topic", "faithfulness", "relevance", "judge_answered"):
        assert k in o, k
    s = _sim("security", [_doc("You useless bot, I hate this!", "Sorry. 18 days [hr-001].")])[0]["quality"]
    assert not {"sentiment_label", "topic", "faithfulness"} & set(s)


def test_typed_fields_are_queryable_in_esql_in_both_projects():
    for project in ("observability", "security"):
        status, resp = Project(project).es("POST", "/_query", {
            "query": "FROM logs-genai_response* | WHERE quality.persona == \"synthetic-test\" "
                     "| KEEP output_verdict, quality.faithfulness, quality.lang_mismatch | LIMIT 1"})
        assert status == 200, str(resp)[:300]
        assert [c["name"] for c in resp["columns"]] == ["output_verdict", "quality.faithfulness", "quality.lang_mismatch"]
