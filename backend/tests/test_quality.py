import pytest

from app.prompt import NO_CONTEXT_ANSWER
from app.quality import cited_ids, context_text, is_answered
from app.retrieval import Doc


@pytest.mark.parametrize("text", [
    "", "   ", NO_CONTEXT_ANSWER,
    "I'm sorry, but the provided documents don't include information about parental leave in Mars.",
    "I’m sorry, but the documents do not contain that.",
    "I don't have information about that.",
    "I cannot find this in the documents.",
    "That is not in the provided documents.",
    "The documents do not mention salary bands for contractors.",
    "I was unable to find an answer.",
])
def test_refusals_are_not_answered(text):
    assert is_answered(text) is False


@pytest.mark.parametrize("text", [
    "You get 18 days of PTO per year [pto-policy].",
    "Remote work is allowed up to 3 days a week [remote-work].",
    "Sorry to hear that. The sick leave policy gives 14 days [sick-leave].",
])
def test_real_answers_are_answered(text):
    assert is_answered(text) is True


def test_cited_ids_only_retrieved_deduped_and_lists_split():
    ans = "See [pto-policy], also [remote, pto-policy; ghost] and [not-a-doc] and [1]."
    assert cited_ids(ans, ["pto-policy", "remote"]) == ["pto-policy", "remote"]
    assert cited_ids("", ["a"]) == [] and cited_ids("no cites", ["a"]) == []


def test_context_text_titles_snippets_and_cap():
    docs = [Doc("a", "Title A", "public", "x" * 5000, 1.0), Doc("b", "Title B", "public", "body b", 0.5)]
    t = context_text(docs)
    assert t.startswith("[a] Title A: xxx") and len(t) <= 6000
    assert "[b] Title B: body b" in context_text(docs[1:])


def test_split_hidden_carries_catalog_score():
    from app.retrieval import split_hidden
    hits = [{"_id": "h", "_score": 0.42, "_source": {"title": "H", "classification": "restricted", "allowed_roles": ["manager"]}},
            {"_id": "n", "_source": {"title": "N", "classification": "restricted", "allowed_roles": []}}]
    g = split_hidden(hits, "employee")
    assert [x.score for x in g] == [0.42, 0.0]
