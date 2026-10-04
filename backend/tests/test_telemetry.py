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
