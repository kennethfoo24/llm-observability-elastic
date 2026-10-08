import json
from datetime import datetime, timedelta, timezone

from feeder import __main__ as cli
from feeder import catalog, engine, profile, registry
from feeder.es import KeyClient, MissingKey

UTC = timezone.utc
T0 = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)  # Monday 11:00 Singapore


class FakeClient:
    """Minimal ES stand-in: bulk(create) with 409 on duplicate ids, state docs in a dict."""

    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.state: dict[str, dict] = {}
        self.bulks = []

    def bulk(self, lines):
        self.bulks.append(len(lines) // 2)
        items = []
        for i in range(0, len(lines), 2):
            meta, doc = lines[i]["create"], lines[i + 1]
            k = (meta["_index"], meta["_id"])
            if k in self.docs:
                items.append({"create": {"status": 409}})
            else:
                self.docs[k] = doc
                items.append({"create": {"status": 201}})
        return 200, {"errors": False, "items": items}

    def es(self, method, path, json=None):  # noqa: A002
        if path.startswith(f"/{engine.STATE_INDEX}/_doc/"):
            key = path.rsplit("/", 1)[1]
            if method == "GET":
                return (200, {"found": True, "_source": self.state[key]}) if key in self.state else (404, {"found": False})
            self.state[key] = json
            return 200, {}
        return 200, {}


def test_catalog_has_stage1_ai_packages_and_template_files():
    registry.load_all()
    assert "ai" in catalog.groups()
    names = {p.name: p for p in catalog.packages("ai")}
    assert {"claude_code", "openai_chatgpt_enterprise", "azure_openai", "anthropic_metrics", "openai", "anthropic", "gcp_vertexai"} <= set(names)
    assert len(names["openai_chatgpt_enterprise"].streams) == 8 and len(names["openai"].streams) == 10
    for s in catalog.streams("ai"):
        assert s.template_path.exists() or s.dir == "billing", s.key
        assert s.pipeline.endswith(s.version)
    cc = [s for s in catalog.streams("ai") if s.package == "claude_code"][0]
    assert cc.index == "logs-claude_code.events.otel-default"


def test_profile_is_deterministic_and_shaped():
    a = [profile.rng_for("x", 1).random() for _ in range(3)]
    assert a == [profile.rng_for("x", 1).random() for _ in range(3)]
    assert profile.rng_for("x", 1).random() != profile.rng_for("x", 2).random()
    weekday_noon = datetime(2026, 10, 5, 5, 30, tzinfo=UTC)  # 13:30 SGT Monday
    night = datetime(2026, 10, 5, 19, 0, tzinfo=UTC)         # 03:00 SGT Tuesday
    weekend = datetime(2026, 10, 3, 5, 30, tzinfo=UTC)       # Saturday 13:30 SGT
    assert profile.activity(weekday_noon) > 5 * profile.activity(night)
    assert profile.activity(weekday_noon) > 2 * profile.activity(weekend)
    rng = profile.rng_for("e")
    errs = sum(profile.is_error(rng, 0.02) for _ in range(5000))
    assert 50 < errs < 160  # about 2 percent
    tin, tout = profile.token_pair(profile.rng_for("t"))
    assert profile.cost_usd("gpt-4o-mini-2024-07-18", tin, tout) < profile.cost_usd("claude-opus-4-5", tin, tout)
    assert profile.latency_ms(profile.rng_for("l"), "gpt-4o-2024-08-06", 2000) > profile.latency_ms(profile.rng_for("l"), "gpt-4o-2024-08-06", 20)


def _gen(key):
    return next(g for g in registry.generators("ai") if g.stream.key == key)


def test_generation_is_idempotent_and_ids_are_deterministic():
    g = _gen("openai/completions")
    a = list(engine.generate(g, T0, T0 + timedelta(minutes=30)))
    b = list(engine.generate(g, T0, T0 + timedelta(minutes=30)))
    assert a and [x[0] for x in a] == [x[0] for x in b] and a == b
    assert len({i for i, _ in a}) == len(a)
    # a sub window yields exactly the same documents for the same minutes (backfill and tick agree)
    sub = list(engine.generate(g, T0 + timedelta(minutes=10), T0 + timedelta(minutes=20)))
    assert all(x in a for x in sub)


def test_every_document_is_tagged_synthetic_and_keeps_existing_tags():
    d = engine.tag({"tags": ["forwarded"], "labels": {"a": "b"}})
    assert d["tags"] == ["forwarded", "synthetic", "synthetic-data-feeder"] and d["labels"] == {"a": "b", "synthetic": "true"}
    assert engine.tag({"tags": "x"})["tags"][0] == "x"
    for g in registry.generators("ai"):
        docs = list(engine.generate(g, T0, T0 + timedelta(minutes=45)))
        assert docs, g.stream.key
        _, doc = docs[0]
        assert {"synthetic", "synthetic-data-feeder"} <= set(doc["tags"]) and doc["labels"]["synthetic"] == "true"
        assert doc["data_stream"] == {"type": g.stream.type, "dataset": g.stream.dataset, "namespace": "default"}
        assert doc["@timestamp"].endswith("Z")
        assert "event.dataset" not in doc and (g.stream.dataset.endswith(".otel") or doc["event"]["dataset"] == g.stream.dataset)


def test_log_generators_send_raw_events_and_metric_generators_final_docs():
    for g in registry.generators("ai"):
        _, doc = next(iter(engine.generate(g, T0, T0 + timedelta(minutes=45))))
        if g.stream.package == "claude_code":
            assert doc["event_name"] and doc["attributes"]["user.email"] and doc["resource"]["attributes"]["service.name"] == "claude-code"
        elif g.stream.kind == "log":
            assert isinstance(doc["message"], str) and isinstance(json.loads(doc["message"]), dict), g.stream.key
        elif g.stream.package in ("anthropic_metrics",):
            assert isinstance(json.loads(doc["message"]), dict)  # anthropic_metrics are raw API items run through the pipeline
        else:
            assert "message" not in doc and doc["data_stream"]["type"] == "metrics"


def test_required_dashboard_fields_are_generated():
    now_docs = lambda key: [d for _, d in engine.generate(_gen(key), T0, T0 + timedelta(hours=3))]
    az = now_docs("azure_openai/metrics")[0]["azure"]
    assert {"requests", "generated_tokens", "provisioned_managed_utilization_v2", "time_to_response"} <= set(az["open_ai"])
    assert {"model_deployment_name", "status_code", "stream_type"} <= set(az["dimensions"])
    cc = now_docs("claude_code/events")
    assert {"api_request", "tool_result", "tool_decision"} <= {d["event_name"] for d in cc}
    req = next(d for d in cc if d["event_name"] == "api_request")["attributes"]
    assert req["cost_usd"] > 0 and req["input_tokens"] > 0 and req["duration_ms"] > 0
    ad = now_docs("anthropic_metrics/usage")
    assert "cache_read_input_tokens" in json.loads(ad[0]["message"])


def test_write_ignores_409_conflicts_and_batches_500():
    g = _gen("claude_code/events")
    docs = list(engine.generate(g, T0, T0 + timedelta(hours=6)))
    assert len(docs) > 500
    c = FakeClient()
    r1 = engine.write(c, g.stream.index, docs)
    assert r1["created"] == len(docs) and r1["errors"] == 0 and max(c.bulks) == 500
    r2 = engine.write(c, g.stream.index, docs)
    assert r2["created"] == 0 and r2["conflicts"] == len(docs) and r2["errors"] == 0
    assert len(c.docs) == len(docs)


def test_write_counts_failure_store_as_error():
    class FS(FakeClient):
        def bulk(self, lines):
            return 200, {"errors": False, "items": [{"create": {"status": 201, "failure_store": "used"}}]}
    r = engine.write(FS(), "logs-x-default", [("1", {"a": 1})])
    assert r["errors"] == 1 and r["created"] == 0


def test_plan_window_heals_gaps_up_to_seven_days():
    now = T0 + timedelta(seconds=30)
    assert engine.plan_window(None, now, 5) == (T0 - timedelta(minutes=5), T0)
    assert engine.plan_window(T0 - timedelta(minutes=7), now, 5) == (T0 - timedelta(minutes=7), T0)
    start, end = engine.plan_window(T0 - timedelta(days=30), now, 5)
    assert end - start == timedelta(days=7)


def test_tick_advances_state_is_idempotent_and_respects_cap():
    g = _gen("openai/completions")
    c = FakeClient()
    now = T0 + timedelta(hours=6)
    c.state["openai__completions"] = {"last_covered": profile.iso(now - timedelta(hours=3))}
    r1 = engine.tick(c, [g], now, 5, max_docs=10_000)
    assert r1["created"] > 0 and r1["errors"] == 0
    assert c.state["openai__completions"]["last_covered"].startswith(engine.profile.iso(now)[:16])
    n = len(c.docs)
    r2 = engine.tick(c, [g], now, 5)  # same instant: nothing new
    assert r2["created"] == 0 and len(c.docs) == n
    c.state["openai__completions"]["last_covered"] = profile.iso(now - timedelta(hours=1))  # replay a covered hour
    r3 = engine.tick(c, [g], now, 5)
    assert r3["created"] == 0 and r3["conflicts"] > 0 and len(c.docs) == n
    # gap heal: a long outage is filled up to the per run cap, then continues on the next run
    c2 = FakeClient()
    c2.state["openai__completions"] = {"last_covered": profile.iso(now - timedelta(days=2))}
    part = engine.tick(c2, [g], now, 5, max_docs=50)
    assert part["created"] <= 50 and part["remaining_budget"] == 0
    assert c2.state["openai__completions"]["last_covered"] < profile.iso(now)
    while engine.tick(c2, [g], now, 5, max_docs=500)["created"]:
        pass
    assert c2.state["openai__completions"]["last_covered"] == profile.iso(now)


def test_tick_does_not_advance_state_on_write_errors():
    class Bad(FakeClient):
        def bulk(self, lines):
            return 500, "boom"
    c = Bad()
    r = engine.tick(c, [_gen("openai/completions")], T0 + timedelta(hours=1), 5, log=lambda *_: None)
    assert r["errors"] > 0 and "openai__completions" not in c.state


def test_tick_cli_fails_clearly_without_key(monkeypatch, capsys):
    monkeypatch.delenv("FEEDER_KEY", raising=False)
    monkeypatch.setenv("OBS_ES_URL", "https://example.invalid")
    assert cli.main(["tick", "--group", "ai"]) == 2
    err = capsys.readouterr().err
    assert "FEEDER_KEY is not set" in err and "feeder_key" in err
    monkeypatch.delenv("OBS_ES_URL")
    assert cli.main(["tick", "--group", "all"]) == 2


def test_keyclient_from_env_never_exposes_the_key(monkeypatch):
    monkeypatch.setenv("OBS_ES_URL", "https://es.invalid/")
    monkeypatch.setenv("FEEDER_KEY", "s3cret")
    c = KeyClient.from_env()
    assert "s3cret" not in repr(c.__dict__.get("_url", "")) and c._headers()["Authorization"] == "ApiKey s3cret"


def test_list_and_registry_groups(capsys):
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "group ai" in out and "claude_code" in out
    assert "ai" in registry.groups()
    total = sum(g.rate_per_min if g.mode == "events" else g.entities / g.every_min for g in registry.generators("ai"))
    assert total < 80  # stage 1 budget: fewer than 400 docs per 5 minute tick at peak load
