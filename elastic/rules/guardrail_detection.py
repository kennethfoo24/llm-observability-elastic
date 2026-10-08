def rule_body() -> dict:
    return {
        "rule_id": "glassbox-flagged-prompts",
        "name": "LLM Observability: flagged LLM prompt",
        "description": "A prompt scored FLAGGED by the Elasticsearch-hosted guardrail models (prompt injection or PII).",
        "type": "query", "language": "kuery",
        "index": ["logs-genai_guardrail*"],
        "query": 'attributes.security.threat_verdict : "FLAGGED"',
        "risk_score": 73, "severity": "high",
        "interval": "1m", "from": "now-6m", "to": "now", "enabled": True, "max_signals": 100,
        "tags": ["GenAI", "Guardrail", "LLM Observability"],
        "alert_suppression": {"group_by": ["attributes.app.persona"], "duration": {"value": 5, "unit": "m"}},
    }
