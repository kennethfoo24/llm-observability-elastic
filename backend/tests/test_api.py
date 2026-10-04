import pytest
from fastapi.testclient import TestClient

from app.chat_service import Deps
from app.config import Settings
from app.guardrail import GuardrailResult, Verdict
from app.llm_sdk import GemmaOffline, LLMResult
from app.main import create_app
from app.models import ModelSpec
from app.retrieval import Doc, RetrievalResult

SPECS = {"flash-lite": ModelSpec("flash-lite", "Flash-Lite", "vertex", "gemini-3.1-flash-lite"),
         "gemma": ModelSpec("gemma", "Gemma", "gemma", "google/gemma-4-31B-it"),
         "noprice": ModelSpec("noprice", "NoPrice", "vertex", "not-in-prices"),
         "boom": ModelSpec("boom", "Boom", "vertex", "gemini-3.1-flash-lite")}
PRICES = {"models": {"gemini-3.1-flash-lite": {"input_per_mtok": 0.25, "output_per_mtok": 1.5}}}


class Ret:
    calls = 0
    def search(self, p, t):
        Ret.calls += 1
        return RetrievalResult([Doc("pto", "PTO", "public", "18 days", 1.0)], [], 3)


class Guard:
    def check(self, t): return GuardrailResult(Verdict("CLEAN", [], 0.0, 0), "ok", 5)


class Sdk:
    calls = 0
    def generate(self, spec, s, u):
        Sdk.calls += 1
        if spec.provider == "gemma":
            raise GemmaOffline("off")
        if spec.key == "boom":
            raise RuntimeError("secret request content here")
        return LLMResult("ok", spec.model_id, 10, 5, 0, "sdk")


class FakeGate:
    def is_up(self): return False

    def require(self): raise GemmaOffline("off")


@pytest.fixture
def client(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://e", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    Ret.calls = Sdk.calls = 0
    s = Settings(_env_file=None, app_password="demo-pw")
    deps = Deps(Ret(), Guard(), Sdk(), None, SPECS, PRICES, emit_log=lambda **kw: None)
    return TestClient(create_app(deps, s, gate=FakeGate()))


H = {"X-Demo-Password": "demo-pw"}
BODY = {"message": "pto days?", "persona": "employee", "model": "flash-lite", "engine": "sdk"}


def test_healthz_is_open_but_api_needs_password(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/personas").status_code == 401
    assert client.get("/api/personas", headers=H).status_code == 200


@pytest.mark.parametrize("path", ["/api/personas", "/api/models", "/api/health/gemma"])
def test_all_api_get_routes_need_password(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Demo-Password": "wrong"}).status_code == 401
    assert client.get(path, headers=H).status_code == 200


def test_chat_needs_password(client):
    assert client.post("/api/chat", json=BODY).status_code == 401
    assert Ret.calls == 0


def test_no_password_configured_leaves_api_open(monkeypatch):
    for k, v in {"OBS_ES_URL": "https://e", "OBS_ES_ADMIN_KEY": "k", "OBS_KIBANA_URL": "https://k"}.items():
        monkeypatch.setenv(k, v)
    deps = Deps(Ret(), Guard(), Sdk(), None, SPECS, PRICES, emit_log=lambda **kw: None)
    c = TestClient(create_app(deps, Settings(_env_file=None, app_password=""), gate=FakeGate()))
    assert c.get("/api/personas").status_code == 200


def test_chat_ok(client):
    r = client.post("/api/chat", json=BODY, headers=H)
    assert r.status_code == 200 and r.json()["answer"] == "ok" and r.json()["cost_usd"] > 0


@pytest.mark.parametrize("msg", ["", "   ", "x" * 4001])
def test_bad_messages_rejected_without_backend_calls(client, msg):
    r = client.post("/api/chat", json={**BODY, "message": msg}, headers=H)
    assert r.status_code == 422 and Ret.calls == 0 and Sdk.calls == 0


def test_unknown_persona_and_model(client):
    r = client.post("/api/chat", json={**BODY, "persona": "intern"}, headers=H)
    assert r.status_code == 400 and r.json()["error"] == "unknown_persona"
    r = client.post("/api/chat", json={**BODY, "model": "gpt-9"}, headers=H)
    assert r.status_code == 400 and r.json()["error"] == "unknown_model"
    assert Ret.calls == 0


def test_bad_engine_422(client):
    r = client.post("/api/chat", json={**BODY, "engine": "magic"}, headers=H)
    assert r.status_code == 422 and Ret.calls == 0 and Sdk.calls == 0


def test_gemma_offline_is_fast_503(client):
    r = client.post("/api/chat", json={**BODY, "model": "gemma"}, headers=H)
    assert r.status_code == 503 and r.json()["error"] == "gemma_offline" and "hint" in r.json()


def test_gemma_offline_never_reaches_retriever_or_llm(client):
    r = client.post("/api/chat", json={**BODY, "model": "gemma"}, headers=H)
    assert r.status_code == 503 and Ret.calls == 0 and Sdk.calls == 0


def test_model_missing_from_prices_is_500_pricing_unavailable(client):
    r = client.post("/api/chat", json={**BODY, "model": "noprice"}, headers=H)
    assert r.status_code == 500 and r.json() == {"error": "pricing_unavailable"}


def test_unexpected_llm_error_is_502_without_message(client):
    r = client.post("/api/chat", json={**BODY, "model": "boom"}, headers=H)
    assert r.status_code == 502
    assert r.json() == {"error": "upstream_error", "detail": "RuntimeError"}
    assert "secret" not in r.text


def test_models_endpoint_marks_gemma_unavailable(client):
    models = {m["key"]: m for m in client.get("/api/models", headers=H).json()}
    assert models["flash-lite"]["available"] is True and models["gemma"]["available"] is False


def test_unicode_message_ok(client):
    r = client.post("/api/chat", json={**BODY, "message": "请问年假有几天? 😀 {x}"}, headers=H)
    assert r.status_code == 200


def test_fastapi_native_otlp_autoconfigure_disabled(client):
    # Regression: FastAPI's own env-driven exporter duplicated every span next to opentelemetry-instrument.
    assert client.app._telemetry["auto_configure"] is False
