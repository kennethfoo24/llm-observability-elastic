import pytest
from fastapi.testclient import TestClient

from app.chat_service import Deps
from app.config import Settings
from app.guardrail import GuardrailResult, Verdict
from app.llm_sdk import LLMResult
from app.main import create_app
from app.models import ModelSpec
from app.retrieval import RetrievalResult
from app.security import SECURITY_HEADERS, SlidingWindowLimiter, client_ip

SPECS = {"flash-lite": ModelSpec("flash-lite", "Flash-Lite", "vertex", "gemini-3.1-flash-lite")}
PRICES = {"models": {"gemini-3.1-flash-lite": {"input_per_mtok": 0.25, "output_per_mtok": 1.5}}}


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


def _client(**over):
    s = Settings(_env_file=None, obs_es_url="http://x", obs_es_admin_key="k", obs_kibana_url="https://kb",
                 app_password="pw", **over)
    deps = Deps(_Ret(), _Guard(), _Sdk(), None, SPECS, PRICES, emit_log=lambda **kw: None, gate=_Gate())
    return TestClient(create_app(deps, s, gate=_Gate()))


H = {"X-Demo-Password": "pw"}
BODY = {"message": "pto?", "persona": "employee", "model": "flash-lite", "engine": "sdk"}


def test_limiter_blocks_after_limit_and_recovers_after_window():
    t = [0.0]
    lim = SlidingWindowLimiter(2, 10, now=lambda: t[0])
    assert lim.allow("a") and lim.allow("a") and not lim.allow("a")
    assert lim.retry_after("a") >= 1
    assert lim.allow("b")  # independent keys
    t[0] = 10.5
    assert lim.allow("a")


def test_client_ip_uses_the_hop_added_by_the_load_balancer():
    assert client_ip("10.0.0.5", "203.0.113.9, 130.211.1.1", 1) == "203.0.113.9"
    assert client_ip("10.0.0.5", None, 1) == "10.0.0.5"
    assert client_ip(None, None, 1) == "unknown"
    # a client-forged leftmost entry is ignored: only the hop added by our own proxy counts
    assert client_ip("10.0.0.5", "6.6.6.6, 203.0.113.9, 130.211.1.1", 1) == "203.0.113.9"


def test_security_headers_on_api_ui_and_errors():
    c = _client()
    for r in (c.get("/healthz"), c.get("/api/personas"), c.get("/api/personas", headers=H)):
        for k, v in SECURITY_HEADERS.items():
            assert r.headers.get(k) == v
    assert "frame-ancestors 'none'" in c.get("/healthz").headers["content-security-policy"]
    assert "strict-transport-security" not in c.get("/healthz").headers
    assert "max-age" in c.get("/healthz", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]


def test_chat_rate_limit_returns_429_with_retry_after():
    c = _client(chat_rate_limit_per_min=3)
    codes = [c.post("/api/chat", json=BODY, headers=H).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    r = c.post("/api/chat", json=BODY, headers=H)
    assert r.json() == {"error": "rate_limited"} and int(r.headers["retry-after"]) >= 1
    assert c.get("/healthz").status_code == 200  # health is never limited


def test_repeated_wrong_passwords_lock_the_ip_out_even_with_the_right_one():
    c = _client(auth_fail_limit=3)
    for _ in range(3):
        assert c.get("/api/personas", headers={"X-Demo-Password": "nope"}).status_code == 401
    assert c.get("/api/personas", headers={"X-Demo-Password": "nope"}).status_code == 429
    assert c.get("/api/personas", headers=H).status_code == 429


def test_forged_forwarded_for_does_not_evade_the_lockout():
    c = _client(auth_fail_limit=2)
    for i in range(2):
        c.get("/api/personas", headers={"X-Demo-Password": "x", "X-Forwarded-For": f"9.9.9.{i}, 203.0.113.9, 130.211.0.1"})
    r = c.get("/api/personas", headers={"X-Demo-Password": "x", "X-Forwarded-For": "1.2.3.4, 203.0.113.9, 130.211.0.1"})
    assert r.status_code == 429


def test_static_ui_is_not_rate_limited_and_unknown_api_path_is_gated_not_leaked():
    c = _client(rate_limit_per_min=2)
    assert all(c.get("/healthz").status_code == 200 for _ in range(10))
    assert c.get("/api/nope").status_code == 401
