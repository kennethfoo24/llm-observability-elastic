"""Helpers for the genai_response log: answered detection, citations and the context text the judge grades against."""
import re

from .prompt import NO_CONTEXT_ANSWER

CONTEXT_MAX_CHARS = 12000   # also the genai.context_text log cap (telemetry.py)
SNIPPET_CHARS = 3000        # per document, the text the answering model saw (prompt.py passes full content)

# One place for refusal / "not in the documents" phrasings (lower-cased match).
_REFUSAL_PATTERNS = [re.compile(p) for p in (
    r"\bi('| a)?m sorry\b.{0,80}\b(don'?t|do not|doesn'?t|does not|cannot|can'?t|unable|not)\b",
    r"\b(provided |available )?(documents?|context|sources?)\b.{0,60}\b(don'?t|do not|doesn'?t|does not|not)\s+(include|contain|mention|cover|provide|have|specify)",
    r"\bnot (found )?in the (provided |available )?(documents?|context)\b",
    r"\bi (don'?t|do not) have (any |enough |that |specific )?(information|details|data|access)",
    r"\bi (couldn'?t|could not|cannot|can'?t|am unable to|was unable to|wasn'?t able to) (find|locate|answer|determine)",
    r"\bno (information|mention|details?|record) (is |was )?(available|found|provided|about)\b",
    r"\bcouldn'?t find anything\b",
    r"\b(unable|not able) to (find|answer|provide)\b",
)]


def is_answered(answer: str) -> bool:
    text = (answer or "").strip()
    if not text or text == NO_CONTEXT_ANSWER:
        return False
    low = text.lower().replace("’", "'")
    return not any(p.search(low) for p in _REFUSAL_PATTERNS)


_BRACKET = re.compile(r"\[([^\[\]\n]{1,200})\]")


def cited_ids(answer: str, retrieved_ids: list[str]) -> list[str]:
    """Ids cited as [doc-id] (or [a, b] / [a; b]) in the answer that were actually retrieved, in order."""
    known = set(retrieved_ids)
    out: list[str] = []
    for m in _BRACKET.finditer(answer or ""):
        for tok in re.split(r"[,;]", m.group(1)):
            tok = tok.strip()
            if tok in known and tok not in out:
                out.append(tok)
    return out


def context_text(docs) -> str:
    parts = [f"[{d.id}] {d.title}: {d.content[:SNIPPET_CHARS]}" for d in docs]
    return "\n".join(parts)[:CONTEXT_MAX_CHARS]
