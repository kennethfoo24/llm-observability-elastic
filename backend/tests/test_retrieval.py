from app.retrieval import Retriever, build_query, split_hidden


def test_query_is_hybrid_rrf_with_rerank():
    body = build_query("how many PTO days", size=4, window=20)
    rerank = body["retriever"]["text_similarity_reranker"]
    assert rerank["inference_id"] == ".jina-reranker-v3"
    assert rerank["inference_text"] == "how many PTO days"
    legs = rerank["retriever"]["rrf"]["retrievers"]
    kinds = {next(iter(leg["standard"]["query"])) for leg in legs}
    assert kinds == {"match", "semantic"}
    assert body["size"] == 4
    assert "content" in body["_source"]


def test_split_hidden_keeps_only_docs_persona_cannot_read():
    hits = [
        {"_id": "pto", "_source": {"title": "PTO", "classification": "public", "allowed_roles": ["employee", "manager"]}},
        {"_id": "aurora", "_source": {"title": "Aurora", "classification": "restricted", "allowed_roles": ["exec"]}},
    ]
    ghosts = split_hidden(hits, "employee")
    assert [g.id for g in ghosts] == ["aurora"]
    assert ghosts[0].classification == "restricted"


class FakeEs:
    def __init__(self, hits):
        self.hits, self.calls = hits, []

    def search(self, **kw):
        self.calls.append(kw)
        return {"took": 7, "hits": {"hits": self.hits}}


def _run_search():
    visible = [{"_id": "pto", "_score": 3.2, "_source": {"title": "PTO", "classification": "public",
               "content": "18 days", "allowed_roles": ["employee"]}}]
    catalog = [{"_id": "aurora", "_source": {"title": "Aurora", "classification": "restricted",
                "allowed_roles": ["exec"]}}]
    made = {}

    def factory(url, key):
        made[key] = FakeEs(visible if key == "emp-key" else catalog)
        return made[key]

    r = Retriever("https://es", {"employee": "emp-key", "catalog": "cat-key"}, client_factory=factory)
    return r.search("employee", "pto"), made


def test_search_uses_persona_key_for_docs_and_catalog_key_for_ghosts():
    result, made = _run_search()
    assert [d.id for d in result.docs] == ["pto"] and result.docs[0].score == 3.2
    assert [g.id for g in result.hidden] == ["aurora"]
    assert result.took_ms == 7
    assert set(made) == {"emp-key", "cat-key"}
    assert "retriever" in made["emp-key"].calls[0]
    assert made["cat-key"].calls[0]["source_includes"] == ["title", "classification", "allowed_roles"]
    assert "source_includes" not in made["emp-key"].calls[0]


def test_catalog_call_never_requests_content_source():
    _, made = _run_search()
    assert "content" not in made["cat-key"].calls[0]["source_includes"]


def test_search_with_no_visible_docs_returns_empty_docs_not_error():
    r = Retriever("https://es", {"employee": "e", "catalog": "c"}, client_factory=lambda u, k: FakeEs([]))
    result = r.search("employee", "reorg")
    assert result.docs == [] and result.hidden == []


def test_unknown_persona_key_raises_keyerror():
    r = Retriever("https://es", {"catalog": "c"}, client_factory=lambda u, k: FakeEs([]))
    import pytest
    with pytest.raises(KeyError):
        r.search("intern", "x")
