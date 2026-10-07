"""Security detection rules over the `genai_response` output verdict (OWASP LLM02, LLM05, LLM07).
Payload shape copied from guardrail_detection.py (accepted by the Security API)."""

_SPECS = [
    # rule_id, name, reason, owasp, risk title, severity, risk_score, mitre
    ("glassbox-llm02-pii-in-response", "Glass Box: LLM02 PII in model response", "pii_in_response", "LLM02",
     "Sensitive information disclosure", "high", 73, "MITRE ATLAS AML.T0057 (LLM Data Leakage)"),
    ("glassbox-llm05-unsafe-output", "Glass Box: LLM05 unsafe markup in model response", "unsafe_markup", "LLM05",
     "Improper output handling", "medium", 47, "MITRE ATT&CK T1059 (Command and Scripting Interpreter)"),
    ("glassbox-llm07-system-prompt-leak", "Glass Box: LLM07 system prompt leakage", "system_prompt_leak", "LLM07",
     "System prompt leakage", "high", 73, "MITRE ATLAS AML.T0056 (LLM Meta Prompt Extraction)"),
]
RULE_IDS = [s[0] for s in _SPECS]


def rule_bodies() -> list[dict]:
    out = []
    for rule_id, name, reason, owasp, title, severity, risk, mitre in _SPECS:
        out.append({
            "rule_id": rule_id, "name": name,
            "description": (f"OWASP {owasp} {title}: the Elasticsearch genai-quality pipeline scored a model "
                            f"response with reason {reason}. {mitre}."),
            "type": "query", "language": "kuery",
            "index": ["logs-genai_response*"],
            "query": f'output_reasons : "{reason}"',
            "risk_score": risk, "severity": severity,
            "interval": "1m", "from": "now-5m", "to": "now", "enabled": True, "max_signals": 100,
            "tags": ["GenAI", "Glass Box", f"OWASP {owasp}"],
        })
    return out
