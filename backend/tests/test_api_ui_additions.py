import pytest
from fastapi.testclient import TestClient

from app.chat_service import Deps
from app.config import Settings
from app.guardrail import GuardrailResult, Verdict
from app.llm_sdk import LLMResult
from app.main import create_app
from app.models import ModelSpec
from app.retrieval import RetrievalResult

SPECS = {"eis-gemini-flash": ModelSpec("eis-gemini-flash", "Gemini 3.5 Flash", "eis", "gemini-3.5-flash")}
PRICES = {"models": {"gemini-3.5-flash": {"input_per_mtok": 0.25, "output_per_mtok": 1.5}}}


class _Ret:
    def search(self, p, t):
        return RetrievalResult([], [], 1)


class _Guard:
    def check(self, t):
        return GuardrailResult(Verdict("CLEAN", [], 0.0, 0), "ok", 1)


class _Sdk:
    def generate(self, spec, s, u):
        return LLMResult("ok", spec.model_id, 1, 1, 0, "sdk")


class _Gate:
    def is_up(self):
        return True

    def require(self):
        return None


def _client(tmp_path=None, password="pw"):
    s = Settings(_env_file=None, obs_es_url="http://x", obs_es_admin_key="k",
                 obs_kibana_url="https://kb.example/", app_password=password)
    deps = Deps(_Ret(), _Guard(), _Sdk(), None, SPECS, PRICES, emit_log=lambda **kw: None, gate=_Gate())
    return TestClient(create_app(deps, s, gate=_Gate(), static_dir=tmp_path))


H = {"X-Demo-Password": "pw"}


def test_config_returns_kibana_url_without_trailing_slash_and_requires_password():
    c = _client()
    assert c.get("/api/config").status_code == 401
    body = c.get("/api/config", headers=H).json()
    assert body == {"kibana_url": "https://kb.example", "security_kibana_url": None, "company": "Foo Corp",
                    "guardrail_models": {"injection": "protectai__deberta-v3-base-prompt-injection-v2",
                                         "ner": "elastic__distilbert-base-cased-finetuned-conll03-english"},
                    "guardrail_pipeline": "genai-guardrail",
                    "quality_pipeline": "genai-quality"}


def test_personas_include_clearance_counts_from_the_corpus_manifest():
    people = {p["id"]: p for p in _client().get("/api/personas", headers=H).json()}
    assert set(people) == {"employee", "manager"}
    assert {p["total_docs"] for p in people.values()} == {20}
    assert [people[i]["can_read_docs"] for i in ("employee", "manager")] == [6, 11]
    assert people["employee"]["name"] and people["employee"]["title"]


def test_static_dir_is_served_at_root_without_password_and_api_stays_gated(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>glassbox</title>")
    c = _client(tmp_path)
    assert "glassbox" in c.get("/").text
    assert c.get("/api/personas").status_code == 401
    assert c.get("/healthz").status_code == 200


def test_missing_static_dir_is_ignored(tmp_path):
    c = _client(tmp_path / "does-not-exist")
    assert c.get("/healthz").status_code == 200
    assert c.get("/").status_code == 404


def test_default_dist_resolves_for_checkout_and_image_layouts(tmp_path):
    from app.main import default_dist
    # checkout layout: <root>/backend/app/main.py -> <root>/frontend/dist
    (tmp_path / "co/backend/app").mkdir(parents=True)
    (tmp_path / "co/frontend/dist").mkdir(parents=True)
    (tmp_path / "co/frontend/dist/index.html").write_text("x")
    assert default_dist(tmp_path / "co/backend/app/main.py") == tmp_path / "co/frontend/dist"
    # image layout: /srv/app/main.py -> /srv/frontend/dist
    (tmp_path / "img/app").mkdir(parents=True)
    (tmp_path / "img/frontend/dist").mkdir(parents=True)
    (tmp_path / "img/frontend/dist/index.html").write_text("x")
    assert default_dist(tmp_path / "img/app/main.py") == tmp_path / "img/frontend/dist"


def test_config_exposes_security_kibana_url_when_set():
    s = Settings(_env_file=None, obs_es_url="http://x", obs_es_admin_key="k", obs_kibana_url="https://kb.example/",
                 sec_kibana_url="https://sec.example/", app_password="")
    deps = Deps(_Ret(), _Guard(), _Sdk(), None, SPECS, PRICES, emit_log=lambda **kw: None, gate=_Gate())
    body = TestClient(create_app(deps, s, gate=_Gate(), static_dir=None)).get("/api/config").json()
    assert body["security_kibana_url"] == "https://sec.example"


class _FindingsEs:
    def __init__(self, hits=None, boom=False):
        self.hits, self.boom, self.seen = hits or [], boom, None

    def search(self, **kw):
        self.seen = kw
        if self.boom:
            raise RuntimeError("down")
        return {"hits": {"hits": self.hits}}


def _findings_client(es):
    s = Settings(_env_file=None, obs_es_url="http://x", obs_es_admin_key="k", obs_kibana_url="https://kb.example/", app_password="pw")
    deps = Deps(_Ret(), _Guard(), _Sdk(), None, SPECS, PRICES, emit_log=lambda **kw: None, gate=_Gate(), findings_es=es)
    return TestClient(create_app(deps, s, gate=_Gate()), headers={"X-Demo-Password": "pw"})


TID = "a" * 32


def test_findings_rejects_a_malformed_trace_id():
    assert _findings_client(_FindingsEs()).get("/api/findings/not-a-trace").status_code == 400


def test_findings_pending_until_the_response_log_exists():
    r = _findings_client(_FindingsEs()).get(f"/api/findings/{TID}").json()
    assert r == {"status": "pending", "security": [], "quality": []}


def test_findings_lists_only_what_triggered_and_never_returns_text():
    src = {"output_verdict": "FLAGGED", "output_reasons": ["unsafe_markup", "pii_in_response"],
           "quality": {"answered": False, "lang_mismatch": False, "off_topic": True, "user_sentiment": "negative"}}
    es = _FindingsEs([{"_source": src}])
    r = _findings_client(es).get(f"/api/findings/{TID}").json()
    assert r["status"] == "ready"
    assert r["security"] == ["unsafe_markup", "pii_in_response"]
    assert r["quality"] == ["not_answered", "off_topic", "negative_sentiment"]
    assert es.seen["query"] == {"term": {"trace_id": TID}}


def test_findings_clean_answer_has_no_findings_and_flattened_keys_work():
    es = _FindingsEs([{"_source": {"output_reasons": [], "quality.answered": True, "quality.user_sentiment": "neutral"}}])
    assert _findings_client(es).get(f"/api/findings/{TID}").json() == {"status": "ready", "security": [], "quality": []}


def test_findings_degrades_when_elasticsearch_is_down():
    assert _findings_client(_FindingsEs(boom=True)).get(f"/api/findings/{TID}").json()["status"] == "unavailable"
