from app.corpus_data import DOCS
from app.dls import persona_role_descriptor
from app.personas import PERSONAS
from app.retrieval import split_hidden

DEMO_DOC = "salary-bands"


def _visible(role):
    # mirrors the DLS query: terms allowed_roles [role]
    q = persona_role_descriptor(role)[role]["indices"][0]["query"]["terms"]["allowed_roles"]
    return {d["slug"] for d in DOCS if set(q) & set(d["allowed_roles"])}


def test_exactly_two_personas():
    assert [p.id for p in PERSONAS] == ["employee", "manager"]


def test_manager_sees_demo_doc_and_employee_does_not():
    assert DEMO_DOC in _visible("manager")
    assert DEMO_DOC not in _visible("employee")


def test_demo_doc_is_a_ghost_card_for_the_engineer_only():
    hits = [{"_id": d["slug"], "_source": d} for d in DOCS]
    assert DEMO_DOC in {g.id for g in split_hidden(hits, "employee")}
    assert DEMO_DOC not in {g.id for g in split_hidden(hits, "manager")}


def test_hr_and_exec_only_docs_hidden_from_both_personas():
    restricted = [d["slug"] for d in DOCS if "manager" not in d["allowed_roles"]
                  and "employee" not in d["allowed_roles"]]
    assert restricted
    for role in ("employee", "manager"):
        assert not set(restricted) & _visible(role)
