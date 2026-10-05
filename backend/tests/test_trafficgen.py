import json
import random

import httpx
import pytest

from trafficgen.__main__ import MAX_REQUESTS_HARD_CAP, build_plan, main, run
from trafficgen.prompts import BENIGN, INJECTION, PII

MODELS = [
    {"key": "eis-gemini-flash", "available": True},
    {"key": "eis-gpt-mini", "available": True},
    {"key": "eis-claude-haiku", "available": True},
    {"key": "gemma", "available": True},
]


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://app")


def test_prompt_banks_cover_every_persona_and_are_distinct():
    assert set(BENIGN) == {"employee", "manager", "hr", "exec"}
    assert all(len(v) >= 5 for v in BENIGN.values())
    assert len(INJECTION) >= 4 and len(PII) >= 4
    assert not any("—" in p or "–" in p for bank in (*BENIGN.values(), INJECTION, PII) for p in bank)


def test_plan_mix_is_mostly_benign_with_some_attacks():
    rng = random.Random(7)
    kinds = [build_plan(rng, MODELS, gemma_ok=False).kind for _ in range(2000)]
    assert 0.80 < kinds.count("benign") / 2000 < 0.90
    assert 0.07 < kinds.count("injection") / 2000 < 0.13
    assert 0.02 < kinds.count("pii") / 2000 < 0.08


def test_gemma_is_never_chosen_unless_allowed_and_available():
    rng = random.Random(1)
    assert all(build_plan(rng, MODELS, gemma_ok=False).model != "gemma" for _ in range(500))
    off = [{**m, "available": m["key"] != "gemma"} for m in MODELS]
    assert all(build_plan(rng, off, gemma_ok=True).model != "gemma" for _ in range(500))
    assert any(build_plan(random.Random(i), MODELS, gemma_ok=True).model == "gemma" for i in range(500))


def test_run_posts_the_plan_and_summarises_without_leaking_prompts(capsys):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        body = json.loads(req.content)
        seen.append((body, req.headers["x-demo-password"]))
        return httpx.Response(200, json={"blocked": False, "guardrail": {"verdict": "CLEAN"}, "cost_usd": 0.001})

    out = run(_client(handler), random.Random(3), 3, password="pw", gemma_ok=False)
    assert len(out) == 3 and len(seen) == 3
    assert all(pw == "pw" for _, pw in seen)
    printed = capsys.readouterr().out
    for body, _ in seen:
        assert body["message"] not in printed
    assert all(json.loads(line)["status"] == 200 for line in printed.strip().splitlines())


def test_hard_cap_limits_requests_even_if_asked_for_more():
    calls = []

    def handler(req):
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        calls.append(1)
        return httpx.Response(200, json={"blocked": True, "guardrail": {"verdict": "FLAGGED"}, "cost_usd": 0})

    run(_client(handler), random.Random(1), 999, password="pw", gemma_ok=False)
    assert len(calls) == MAX_REQUESTS_HARD_CAP


def test_server_errors_do_not_abort_the_run_but_a_401_is_reported():
    def ok_then_500(req):
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        return httpx.Response(502, json={"error": "upstream_error"})

    out = run(_client(ok_then_500), random.Random(1), 3, password="pw", gemma_ok=False)
    assert [r["status"] for r in out] == [502, 502, 502]

    def unauthorized(req):
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(SystemExit) as e:
        run(_client(unauthorized), random.Random(1), 3, password="bad", gemma_ok=False)
    assert e.value.code == 1


def test_a_429_stops_the_run_politely_instead_of_hammering():
    n = []

    def limited(req):
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        n.append(1)
        return httpx.Response(429, json={"error": "rate_limited"}, headers={"Retry-After": "30"})

    out = run(_client(limited), random.Random(1), 5, password="pw", gemma_ok=False)
    assert len(n) == 1 and out[0]["status"] == 429


def test_unreachable_target_exits_2_with_one_clean_json_line(capsys):
    def boom(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(SystemExit) as e:
        run(_client(boom), random.Random(1), 3, password="pw", gemma_ok=False)
    assert e.value.code == 2
    assert json.loads(capsys.readouterr().out.strip()) == {"event": "unreachable"}


def test_transport_error_after_first_call_ends_gracefully_with_results_so_far(capsys):
    n = []

    def flaky(req):
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        n.append(1)
        if len(n) == 1:
            return httpx.Response(200, json={"blocked": False, "guardrail": {"verdict": "CLEAN"}, "cost_usd": 0.0})
        raise httpx.ReadTimeout("slow", request=req)

    out = run(_client(flaky), random.Random(1), 5, password="pw", gemma_ok=False)
    assert len(out) == 1 and out[0]["status"] == 200 and len(n) == 2
    assert "interrupted" in capsys.readouterr().out


def test_prompt_text_never_appears_in_exception_messages():
    seen = []

    def boom(req):
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        seen.append(json.loads(req.content)["message"])
        raise httpx.ReadTimeout("slow", request=req)

    run(_client(boom), random.Random(2), 2, password="pw", gemma_ok=False)

    def unauthorized(req):
        if req.url.path == "/api/models":
            return httpx.Response(200, json=MODELS)
        seen.append(json.loads(req.content)["message"])
        return httpx.Response(401, json={})

    with pytest.raises(SystemExit) as e:
        run(_client(unauthorized), random.Random(2), 2, password="pw", gemma_ok=False)
    assert all(m not in str(e.value) for m in seen)


def test_main_requires_app_password_with_clear_one_line_error(monkeypatch, capsys):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("TARGET_URL", "http://secret-host.invalid")
    assert main() == 1
    cap = capsys.readouterr()
    text = cap.out + cap.err
    assert "APP_PASSWORD" in text and len(text.strip().splitlines()) == 1
    assert "secret-host" not in text


def test_main_caps_and_sanitises_max_requests(monkeypatch):
    got = []

    def fake_run(client, rng, max_requests, password, gemma_ok):
        got.append((max_requests, password, gemma_ok))
        return []

    monkeypatch.setattr("trafficgen.__main__.run", fake_run)
    monkeypatch.setenv("APP_PASSWORD", "pw")
    for raw, want in [("abc", 1), ("", 1), ("9", 5), ("3", 3), ("-2", 1), ("0", 1)]:
        monkeypatch.setenv("MAX_REQUESTS", raw)
        assert main() == 0
        assert got[-1][0] == want, raw
    monkeypatch.delenv("MAX_REQUESTS")
    assert main() == 0 and got[-1][0] == 1
    monkeypatch.setenv("GEMMA_TRAFFIC", "1")
    main()
    assert got[-1][2] is True


def test_model_mix_is_weighted_toward_the_cheapest_eis_model():
    from collections import Counter
    c = Counter(build_plan(random.Random(i), MODELS, gemma_ok=False).model for i in range(3000))
    assert set(c) == {"eis-gpt-mini", "eis-claude-haiku", "eis-gemini-flash"}
    assert 0.65 < c["eis-gpt-mini"] / 3000 < 0.75
