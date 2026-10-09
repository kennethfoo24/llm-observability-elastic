"""Offline tests of the devtools feeder group (stage 3): NVIDIA GPU (+ OTel), Cursor, GitLab and Slack."""
import json
from datetime import datetime, timedelta, timezone

from feeder import engine, registry

UTC = timezone.utc
T0 = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)  # Monday 11:00 Singapore (busy)
NIGHT = datetime(2026, 10, 5, 19, 0, tzinfo=UTC)  # 03:00 Singapore


def gens():
    return registry.generators("devtools")


def key(g):
    return g.stream.key


def docs_of(k, hours=2, start=T0):
    g = next(x for x in gens() if key(x) == k)
    return [d for _, d in engine.generate(g, start, start + timedelta(hours=hours))]


def raw_json(d):
    return json.loads(d["message"])


def test_group_registers_every_stream():
    assert {key(g) for g in gens()} == {
        "nvidia_gpu/stats", "nvidia_gpu_otel/metrics-nvidia_gpu.otel", "cursor/audit", "gitlab/api", "gitlab/application", "gitlab/audit", "gitlab/auth",
        "gitlab/pages", "gitlab/production", "gitlab/sidekiq", "slack/audit"}


def test_generation_is_deterministic():
    g = next(x for x in gens() if key(x) == "slack/audit")
    a = [d for _, d in engine.generate(g, T0, T0 + timedelta(minutes=30))]
    b = [d for _, d in engine.generate(g, T0, T0 + timedelta(minutes=30))]
    assert a == b and a


def test_every_document_is_tagged_synthetic():
    for g in gens():
        docs = [d for _, d in engine.generate(g, T0, T0 + timedelta(minutes=15))]
        assert docs, key(g)
        for d in docs:
            tags = d.get("tags") or d.get("resource", {}).get("attributes", {}).get("tags")
            assert "synthetic" in tags and "synthetic-data-feeder" in tags, key(g)


# ------------------------------------------------------------------ NVIDIA ----------------------------------------------------------
def test_nvidia_topology_two_nodes_four_gpus_with_stable_uuids():
    docs = docs_of("nvidia_gpu/stats", hours=1)
    uuids = {d["gpu"]["labels"]["uuid"] for d in docs}
    hosts = {d["gpu"]["labels"]["hostname"] for d in docs}
    assert len(uuids) == 8 and hosts == {"gpu-node-a", "gpu-node-b"}


def test_nvidia_training_node_runs_hotter_than_inference_at_night():
    docs = docs_of("nvidia_gpu/stats", hours=2, start=NIGHT)
    util = lambda host: [d["gpu"]["utilization"]["gpu"]["pct"] for d in docs if d["gpu"]["labels"]["hostname"] == host and "err_code" not in d["gpu"]["labels"]]  # noqa: E731
    assert sum(util("gpu-node-a")) / len(util("gpu-node-a")) > 60
    assert sum(util("gpu-node-b")) / len(util("gpu-node-b")) < 30


def test_nvidia_counters_never_decrease_per_gpu():
    docs = [d for d in docs_of("nvidia_gpu/stats", hours=3) if "err_code" not in d["gpu"]["labels"]]
    last = {}
    for d in docs:
        u = d["gpu"]["labels"]["uuid"]
        e = d["gpu"]["power"]["energy_consumption_total"]
        assert e >= last.get(u, 0)
        last[u] = e


def test_nvidia_dashboard_fields_are_present():
    d = docs_of("nvidia_gpu/stats", hours=1)[0]
    g = d["gpu"]
    for path in (("clock", "mem_frequency"), ("clock", "streaming_multiprocessor_frequency"), ("device", "brand"), ("device", "ecc_info_rom_version"),
                 ("device", "vbios_version"), ("labels", "model_name"), ("labels", "hostname"), ("labels", "uuid"), ("memory", "framebuffer", "free_size"),
                 ("memory", "framebuffer", "used_size"), ("power", "energy_consumption_total"), ("power", "usage")):
        cur = g
        for p in path:
            cur = cur[p]
        assert cur is not None
    assert d["service"]["type"] == "prometheus"


def test_nvidia_xid_errors_exist_over_a_week_and_use_the_error_dimension():
    g = next(x for x in gens() if key(x) == "nvidia_gpu/stats")
    week = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    errs = [d for _, d in engine.generate(g, week, week + timedelta(days=7)) if "err_code" in d["gpu"]["labels"]]
    assert 20 < len(errs) < 150
    assert all(d["gpu"]["error"]["xid"] == float(d["gpu"]["labels"]["err_code"]) and d["gpu"]["labels"]["err_msg"] for d in errs)


def test_nvidia_otel_documents_use_the_dcgm_names_and_the_default_namespace():
    docs = docs_of("nvidia_gpu_otel/metrics-nvidia_gpu.otel", hours=1)
    normal = [d for d in docs if "DCGM_FI_DEV_GPU_UTIL" in d["metrics"]]
    assert normal and all(d["data_stream"] == {"type": "metrics", "dataset": "nvidia_gpu.otel", "namespace": "default"} for d in docs)
    d = normal[0]
    assert {"UUID", "Hostname", "modelName", "DCGM_FI_DRIVER_VERSION"} <= set(d["attributes"])
    assert {"DCGM_FI_DEV_FB_USED", "DCGM_FI_DEV_FB_FREE", "DCGM_FI_DEV_POWER_USAGE", "DCGM_FI_DEV_GPU_TEMP", "DCGM_FI_DEV_SM_CLOCK"} <= set(d["metrics"])


# ------------------------------------------------------------------ Cursor ---------------------------------------------------------
def test_cursor_events_are_raw_json_with_the_pipeline_fields():
    docs = docs_of("cursor/audit", hours=6)
    evs = [raw_json(d) for d in docs]
    assert len(evs) > 100
    for e in evs:
        assert {"event_id", "timestamp", "event_type", "ip_address", "user_email", "team_id", "event_data"} <= set(e)
    types = {e["event_type"] for e in evs}
    assert {"login", "logout", "mcp_server_config"} <= types
    assert any(e["event_data"].get("server_name") for e in evs if e["event_type"] == "mcp_server_config")
    assert any(e["event_data"].get("source") for e in evs)


# ------------------------------------------------------------------ GitLab ----------------------------------------------------------
def test_gitlab_api_lines_carry_user_path_status_and_duration():
    for d in docs_of("gitlab/api", hours=1)[:50]:
        o = raw_json(d)
        assert o["username"] and o["user_id"] and o["path"].startswith("/api/v4/") and o["remote_ip"] and o["duration_s"] > 0 and o["meta.caller_id"]


def test_gitlab_application_messages_match_the_dashboard_patterns():
    msgs = [raw_json(d)["message"] for d in docs_of("gitlab/application", hours=24)]
    assert any(m.startswith("Successful Login: username=") for m in msgs) and any(m.startswith("Failed Login: username=") for m in msgs)
    assert any(" created a new project " in m for m in msgs) and any(m.startswith("User ") and m.endswith(" was created") for m in msgs)
    assert any(m.startswith("Group ") and m.endswith(" was removed") for m in msgs) or any(m.startswith("Group ") and m.endswith(" was created") for m in msgs)
    assert any("mergeability_merge_request_id" in raw_json(d) for d in docs_of("gitlab/application", hours=24))


def test_gitlab_every_stream_wraps_the_line_in_message():
    for k in ("gitlab/production", "gitlab/auth", "gitlab/audit", "gitlab/sidekiq", "gitlab/pages"):
        d = docs_of(k, hours=6)[0]
        assert isinstance(d["message"], str) and json.loads(d["message"])


# ------------------------------------------------------------------ Slack -----------------------------------------------------------
def test_slack_events_have_actor_entity_context_and_a_variety_of_actions():
    evs = [raw_json(d) for d in docs_of("slack/audit", hours=12)]
    assert len(evs) > 200
    for e in evs:
        assert {"id", "date_create", "action", "actor", "entity", "context"} <= set(e) and e["context"]["ip_address"]
    assert len({e["action"] for e in evs}) >= 8
    assert any(e["action"] == "anomaly" and "action_timestamp" in e["details"] for e in docs_of("slack/audit", hours=24) and [raw_json(d) for d in docs_of("slack/audit", hours=24)])


def test_volume_stays_inside_the_budget():
    week = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
    total = sum(1 for g in gens() for _ in engine.generate(g, week, week + timedelta(days=7)))
    assert total < 300_000, total
    peak = datetime(2026, 10, 5, 5, 30, tzinfo=UTC)
    n = sum(1 for g in gens() for _ in engine.generate(g, peak, peak + timedelta(minutes=5)))
    assert n < 300, n
