from dataclasses import dataclass, field

from elasticsearch import Elasticsearch
from opentelemetry import trace

from .personas import get_persona

RERANK_ID = ".jina-reranker-v3"
CATALOG_SOURCE_INCLUDES = ["title", "classification", "allowed_roles"]
tracer = trace.get_tracer("glassbox.retrieval")


@dataclass
class Doc:
    id: str
    title: str
    classification: str
    content: str
    score: float


@dataclass
class Ghost:
    id: str
    title: str
    classification: str
    score: float = 0.0  # catalog (RRF) score; 0.0 when unavailable


@dataclass
class RetrievalResult:
    docs: list[Doc] = field(default_factory=list)
    hidden: list[Ghost] = field(default_factory=list)
    took_ms: int = 0


def _rrf(text: str, window: int) -> dict:
    return {"rrf": {"retrievers": [
        {"standard": {"query": {"match": {"content": text}}}},
        {"standard": {"query": {"semantic": {"field": "content_semantic", "query": text}}}},
    ], "rank_window_size": window}}


def build_query(text: str, size: int = 4, window: int = 20) -> dict:
    return {
        "retriever": {"text_similarity_reranker": {
            "retriever": _rrf(text, window),
            "field": "content",
            "inference_id": RERANK_ID,
            "inference_text": text,
            "rank_window_size": window,
        }},
        "size": size,
        "_source": ["title", "classification", "allowed_roles", "content"],
    }


def split_hidden(catalog_hits: list[dict], role: str) -> list[Ghost]:
    return [
        Ghost(h["_id"], h["_source"]["title"], h["_source"]["classification"],
              h.get("_score") or 0.0)
        for h in catalog_hits
        if role not in h["_source"].get("allowed_roles", [])
    ]


def _default_factory(url: str, key: str) -> Elasticsearch:
    return Elasticsearch(url, api_key=key, request_timeout=20)


class Retriever:
    def __init__(self, es_url: str, keys: dict[str, str], index: str = "hr-kb", client_factory=None):
        self._url, self._keys, self._index = es_url, keys, index
        self._factory = client_factory or _default_factory
        self._clients: dict[str, object] = {}

    def _client(self, name: str):
        if name not in self._clients:
            self._clients[name] = self._factory(self._url, self._keys[name])
        return self._clients[name]

    def _catalog_search(self, text: str) -> dict:
        """The ONLY use of the catalog client. It can match on content but must never fetch it,
        so source_includes is always set here."""
        return self._client("catalog").search(
            index=self._index, retriever=_rrf(text, 20), size=8, source_includes=CATALOG_SOURCE_INCLUDES)

    def search(self, persona_id: str, text: str) -> RetrievalResult:
        persona = get_persona(persona_id) if persona_id != "catalog" else None
        if persona is None or persona.id not in self._keys:
            raise KeyError(persona_id)
        with tracer.start_as_current_span("retrieval.hybrid") as span:
            span.set_attribute("app.persona", persona.id)
            resp = self._client(persona.id).search(index=self._index, **build_query(text))
            docs = [Doc(h["_id"], h["_source"]["title"], h["_source"]["classification"],
                        h["_source"]["content"], h.get("_score") or 0.0) for h in resp["hits"]["hits"]]
            catalog = self._catalog_search(text)
            hidden = split_hidden(catalog["hits"]["hits"], persona.role)
            span.set_attribute("retrieval.docs_returned", len(docs))
            span.set_attribute("retrieval.docs_hidden_by_dls", len(hidden))
            return RetrievalResult(docs, hidden, resp.get("took", 0))
