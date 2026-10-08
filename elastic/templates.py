"""Component and index template for the genai_response data stream (typed result fields, see FIELD_MAPPINGS)."""
from app.quality_pipeline import FIELD_MAPPINGS

COMPONENT_NAME = "glassbox-genai-response@mappings"
INDEX_TEMPLATE_NAME = "glassbox-genai-response"
INDEX_PATTERN = "logs-genai_response.otel-*"
DEFAULT_TEMPLATE = "logs-otel@template"
PRIORITY = 130   # above the default otel logs template (120)


def build_component() -> dict:
    return {"template": {"mappings": {"properties": FIELD_MAPPINGS}},
            "_meta": {"description": "LLM Observability: typed output guardrail and quality fields for genai_response logs"}}


def build_index_template(default_template: dict) -> dict:
    """default_template: the body of GET /_index_template/logs-otel@template (index_template part).
    Composed of the same components, plus ours last so our mappings win."""
    composed = [c for c in default_template["composed_of"] if c != COMPONENT_NAME] + [COMPONENT_NAME]
    body = {"index_patterns": [INDEX_PATTERN], "priority": PRIORITY, "data_stream": {}, "composed_of": composed,
            "allow_auto_create": True,
            "_meta": {"description": "LLM Observability: genai_response logs with typed quality fields"}}
    inline = (default_template.get("template") or {}).get("mappings")
    if inline:   # keep the default template's own mappings (data_stream.type constant_keyword)
        body["template"] = {"mappings": inline}
    if default_template.get("ignore_missing_component_templates"):
        body["ignore_missing_component_templates"] = list(default_template["ignore_missing_component_templates"])
    return body
