"""Observability alert: the LLM04 document scan flagged a document or a document changed since its baseline."""
from .cost_alert import esql_rule_body

RULE_ID = "glassbox-doc-integrity"
NAME = "LLM Observability: Document scan flagged or changed"
INDEX = "hr-kb-staging"
CONDITION = 'doc_scan.verdict == "FLAGGED" OR doc_scan.fingerprint != doc_scan.baseline_fingerprint'
BASE = f"FROM {INDEX} | WHERE doc_scan.scanned_at > NOW() - 24 hours AND ({CONDITION})"
CHANGED_ESQL = (f"FROM {INDEX} | WHERE doc_scan.scanned_at > NOW() - 24 hours "
                "AND doc_scan.fingerprint != doc_scan.baseline_fingerprint "
                "| KEEP doc_scan.fingerprint, doc_scan.baseline_fingerprint, title")


def esql(min_docs: int = 1) -> str:
    return f"{BASE} | STATS docs = COUNT(*) | WHERE docs >= {int(min_docs)}"


def rule_body(min_docs: int = 1) -> dict:
    return esql_rule_body(NAME, esql(min_docs), ["glassbox", "owasp", "llm04", "doc-scan"], interval="5m", window_hours=24)
