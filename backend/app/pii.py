import re

# Shared with the ingest pipeline (guardrail_pipeline.py builds grok definitions from these names).
PII_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "nric": r"\b[STFGM]\d{7}[A-Z]\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "phone": r"(?:\+65[ -]?)?\b[89]\d{3}[ -]?\d{4}\b",
    "salary": r"\b\d{2,3}(?:,\d{3})+\b",
}
_COMPILED = {k: re.compile(v) for k, v in PII_PATTERNS.items()}


def find_pii(text: str) -> list[str]:
    return sorted(name for name, rx in _COMPILED.items() if rx.search(text))
