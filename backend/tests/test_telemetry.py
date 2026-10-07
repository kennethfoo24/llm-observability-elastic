import logging

from app.telemetry import emit_prompt_log


def test_emit_prompt_log_carries_attributes_and_prompt_verbatim(caplog):
    prompt = "héllo 👋 日本語 {braces} {0} %s"
    logging.getLogger("genai.guardrail").propagate = True
    with caplog.at_level(logging.INFO, logger="genai.guardrail"):
        emit_prompt_log(prompt=prompt, persona="employee", model="m", engine="sdk", status="ok")
    rec = [r for r in caplog.records if r.name == "genai.guardrail"][0]
    d = rec.__dict__
    assert d["data_stream.dataset"] == "genai_guardrail"
    assert d["genai.prompt_text"] == prompt
    assert d["app.persona"] == "employee" and d["app.genai.model"] == "m"
    assert d["app.genai.engine"] == "sdk" and d["guardrail.status"] == "ok"


def test_emit_response_log_fields_types_and_truncation(caplog):
    from app.telemetry import emit_response_log
    logging.getLogger("genai.guardrail").propagate = True
    with caplog.at_level(logging.INFO, logger="genai.guardrail"):
        emit_response_log(prompt="p" * 5000, response="r" * 5000, context="c" * 7000, retrieved_ids=["a", "b"],
                          cited_ids=["a"], top_score=2, hidden_count=1, top_hidden_score=None, answered=True,
                          persona="manager", model="m", engine="langchain")
    d = [r for r in caplog.records if r.name == "genai.guardrail"][0].__dict__
    assert d["data_stream.dataset"] == "genai_response"
    assert len(d["genai.prompt_text"]) == 4000 and len(d["genai.response_text"]) == 4000
    assert len(d["genai.context_text"]) == 6000
    assert d["genai.retrieved_ids"] == ["a", "b"] and d["genai.cited_ids"] == ["a"]
    assert d["genai.top_score"] == 2.0 and isinstance(d["genai.top_score"], float)
    assert d["genai.hidden_count"] == 1 and d["genai.top_hidden_score"] == 0.0
    assert d["genai.answered"] is True
    assert d["app.persona"] == "manager" and d["app.genai.model"] == "m" and d["app.genai.engine"] == "langchain"
