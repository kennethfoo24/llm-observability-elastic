"""Offline tests of the INFRASTRUCTURE feeder group (nginx, windows, redis, mysql, kafka and the OTel content packages)."""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from feeder import catalog, coverage, engine, registry
from feeder.gen import infra

UTC = timezone.utc
T0 = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)  # Monday 11:00 Singapore
TEMPL = Path(catalog.TEMPLATES)


def gens():
    return registry.generators("infra")


def key(g):
    return g.stream.key


def docs_of(k, hours=3, start=T0):
    g = next(x for x in gens() if key(x) == k)
    return [d for _, d in engine.generate(g, start, start + timedelta(hours=hours))]


def get(d, path):
    """Dotted lookup; OTel attribute maps use flat dotted keys (`attributes["db.query.text"]`), so try the remaining path as one key."""
    parts = path.split(".")
    cur = d
    for i, p in enumerate(parts):
        if not isinstance(cur, dict):
            return None
        if p in cur:
            cur = cur[p]
            continue
        rest = ".".join(parts[i:])
        return cur.get(rest)
    return cur


def test_catalog_and_generators_cover_every_package():
    registry.load_all()
    names = {p.name for p in catalog.packages("infra")}
    assert {"nginx", "nginx_ingress_controller", "nginx_otel", "nginx_ingress_controller_otel", "windows", "redis", "redis_otel", "redisenterprise", "redisenterprise_otel",
            "mysql", "mysql_otel", "kafka", "kafka_connect", "kafka_otel"} <= names
    have_gen = {g.stream.package for g in gens()}
    assert names <= have_gen, names - have_gen
    assert len([s for s in catalog.streams("infra") if s.package == "windows"]) == 11
    assert len([s for s in catalog.streams("infra") if s.package == "kafka"]) == 13
    keys = [key(g) for g in gens()]
    assert len(keys) == len(set(keys)), "state keys must be unique per stream"


def test_templates_and_field_lists_exist_for_integration_streams():
    registry.load_all()
    no_sample = {"windows/perfmon", "windows/service", "redis/log", "redis/slowlog", "kafka/log"}  # no sample_event in the package
    for s in catalog.streams("infra"):
        assert s.template_path.exists() or s.key in no_sample, s.key
        assert infra.fields_path(s.key).exists() or s.key in no_sample or s.key.startswith("windows/") or s.type == "logs", s.key


@pytest.mark.parametrize("g", gens(), ids=key)
def test_every_generator_is_deterministic_tagged_and_shaped(g):
    a = list(engine.generate(g, T0, T0 + timedelta(hours=2)))
    b = list(engine.generate(g, T0, T0 + timedelta(hours=2)))
    assert a and a == b
    ids = [i for i, _ in a]
    assert len(ids) == len(set(ids))
    for _, d in a[:50]:
        tags = d.get("tags") or []
        assert "synthetic" in tags and "synthetic-data-feeder" in tags
        assert d["@timestamp"].endswith("Z")
        assert d["data_stream"]["dataset"] == g.stream.dataset and d["data_stream"]["type"] == g.stream.type
        if g.stream.dataset.endswith(".otel"):  # OTel mappings have no top level tags: the filter keys live in resource.attributes
            ra = d["resource"]["attributes"]
            assert ra["tags"] == ["synthetic", "synthetic-data-feeder"] and ra["labels.synthetic"] == "true"
            assert d["data_stream"]["namespace"] == g.stream.namespace


REQUIRED = {
    "nginx/access": ["message", "host.name", "log.file.path"], "nginx/error": ["message", "host.name"],
    "nginx/stubstatus": ["nginx.stubstatus.requests", "nginx.stubstatus.active", "nginx.stubstatus.hostname", "host.name", "service.address"],
    "nginx_ingress_controller/access": ["message"], "nginx_ingress_controller/error": ["message"],
    "windows/service": ["windows.service.id", "windows.service.state", "windows.service.start_type", "windows.service.display_name", "host.name", "metricset.name"],
    "windows/sysmon_operational": ["winlog.channel", "winlog.event_id", "event.code", "host.name", "process.name", "winlog.computer_name"],
    "windows/forwarded": ["winlog.channel", "event.code", "host.name"], "windows/powershell": ["event.code", "powershell.engine.version", "host.name"],
    "windows/powershell_operational": ["event.code", "winlog.channel", "host.name"],
    "windows/applocker_exe_and_dll": ["event.code", "file.hash.sha256", "file.name", "winlog.user_data.PolicyName", "winlog.user_data.Fqbn", "host.name"],
    "redis/info": ["redis.info.clients.connected", "redis.info.memory.used.value", "redis.info.replication.role", "service.address", "host.name"],
    "redis/keyspace": ["redis.keyspace.id", "redis.keyspace.keys"], "redis/key": ["redis.key.id", "redis.key.type", "redis.keyspace.id"],
    "redis/log": ["message"], "redis/slowlog": ["redis.slowlog.cmd", "redis.slowlog.duration.us"],
    "redisenterprise/node": ["redisenterprise.node.labels.node", "redisenterprise.node.conns.value"], "redisenterprise/proxy": ["redisenterprise.proxy.labels.bdb"],
    "mysql/status": ["mysql.status.queries", "mysql.status.threads.connected", "host.name"], "mysql/replica_status": ["sql.metrics.numeric.seconds_behind_source", "host.name"],
    "mysql/galera_status": ["mysql.galera_status.cluster.size"], "mysql/performance": ["host.name"], "mysql/slowlog": ["message"], "mysql/error": ["message"],
    "kafka/broker": ["kafka.broker.id", "kafka.broker.address", "host.name"], "kafka/consumergroup": ["kafka.consumergroup.id", "kafka.consumergroup.consumer_lag", "kafka.topic.name", "kafka.partition.id"],
    "kafka/partition": ["kafka.partition.offset.newest", "kafka.topic.name"], "kafka/topic": ["kafka.topic.topic.name", "kafka.topic.log.size"],
    "kafka/jvm": ["kafka.jvm.gc.name", "kafka.jvm.memory.heap_usage.used"], "kafka/network": ["kafka.network.request_metrics.request_type"], "kafka/raft": ["kafka.raft.current_state"],
    "kafka/controller": ["kafka.controller.kafka_controller.active_controller_count"], "kafka/log": ["message"],
    "kafka_connect/connector": ["kafka_connect.mbean", "kafka_connect.connector.status"], "kafka_connect/task": ["kafka_connect.mbean"],
    "nginx_otel/metrics-nginxreceiver.otel": ["metrics", "_metric_names_hash", "resource.attributes.host.name", "scope.name"],
    "nginx_otel/logs-nginx.access.otel": ["attributes.http.response.status_code", "attributes.url.original", "resource.attributes.host.name"],
    "nginx_ingress_controller_otel/logs-nginx_ingress_controller.access.otel": ["body.structured.upstream.name", "body.structured.url.path"],
    "redis_otel/metrics-redisreceiver.otel": ["metrics", "resource.attributes.host.name"],
    "redisenterprise_otel/metrics-redisenterprise.otel": ["metrics", "_metric_names_hash"],
    "mysql_otel/metrics-mysqlreceiver.otel": ["metrics", "resource.attributes.mysql.instance.endpoint"], "mysql_otel/logs-mysqlreceiver.otel": ["attributes.db.query.text", "event_name"],
    "kafka_otel/metrics-kafkametricsreceiver.otel": ["metrics", "scope.name"],
}


@pytest.mark.parametrize("k", sorted(REQUIRED))
def test_required_fields_per_stream(k):
    ds = docs_of(k)
    assert ds, k
    for d in ds[:60]:
        for f in REQUIRED[k]:
            assert get(d, f) not in (None, ""), (k, f)


def test_topology_nginx_windows_redis_mysql_kafka():
    assert infra.NGINX_HOSTS == ["web-sin-01", "web-sin-02", "web-sin-03"] and len(infra.WINDOWS_HOSTS) == 5
    assert [n for n, _ in infra.REDIS_NODES] == ["redis-cache-01", "redis-cache-02"]
    assert Counter(r for _, r in infra.MYSQL_NODES) == {"primary": 1, "replica": 2}
    assert infra.KAFKA_BROKERS == [1, 2, 3] and len(infra.KAFKA_TOPICS) == 12 and len(set(infra.KAFKA_TOPICS)) == 12
    assert {d["host"]["name"] for d in docs_of("nginx/access", 6)} == set(infra.NGINX_HOSTS)
    assert {d["host"]["name"] for d in docs_of("windows/service", 2)} == {h for h in infra.WINDOWS_HOSTS}
    assert {d["host"]["name"] for d in docs_of("redis/info", 1)} == {"redis-cache-01", "redis-cache-02"}
    roles = {d["redis"]["info"]["replication"]["role"] for d in docs_of("redis/info", 1)}
    assert roles == {"master", "slave"}
    assert {d["host"]["name"] for d in docs_of("mysql/status", 1)} == {n for n, _ in infra.MYSQL_NODES}
    assert {d["host"]["name"] for d in docs_of("mysql/replica_status", 1)} == {"mysql-replica-01", "mysql-replica-02"}
    assert {d["kafka"]["broker"]["id"] for d in docs_of("kafka/partition", 12)} == {1, 2, 3}
    assert {d["kafka"]["topic"]["name"] for d in docs_of("kafka/partition", 12)} == set(infra.KAFKA_TOPICS)
    groups = {d["kafka"]["consumergroup"]["id"] for d in docs_of("kafka/consumergroup", 12)}
    assert groups == {g for g, _ in infra.KAFKA_GROUPS}


def test_numbers_are_correlated_not_random_noise():
    stub = sorted(((d["@timestamp"], d["host"]["name"], d["nginx"]["stubstatus"]["requests"]) for d in docs_of("nginx/stubstatus", 12)))
    per = {}
    for ts, h, r in stub:
        per.setdefault(h, []).append(r)
    for h, vals in per.items():
        assert vals == sorted(vals), f"requests is a counter and must grow ({h})"
    rs = docs_of("mysql/replica_status", 12)
    assert all(d["sql"]["metrics"]["numeric"]["exec_source_log_pos"] <= d["sql"]["metrics"]["numeric"]["read_source_log_pos"] for d in rs)
    day = [d for d in docs_of("kafka/consumergroup", 2) if d["kafka"]["consumergroup"]["id"] == "analytics-ingest"]
    night = [d for d in docs_of("kafka/consumergroup", 2, datetime(2026, 10, 5, 19, 0, tzinfo=UTC)) if d["kafka"]["consumergroup"]["id"] == "analytics-ingest"]
    assert sum(d["kafka"]["consumergroup"]["consumer_lag"] for d in day) / len(day) > 3 * sum(d["kafka"]["consumergroup"]["consumer_lag"] for d in night) / len(night)
    st = Counter(get(d, "http.response.status_code") or 0 for d in docs_of("nginx_ingress_controller/access", 4))
    assert st  # raw lines: the status code is only parsed by the pipeline, but the message carries it
    codes = Counter(int(d["message"].split('" ')[1].split()[0]) for d in docs_of("nginx/access", 6))
    assert codes[200] > 0.7 * sum(codes.values()) and 0 < sum(v for c, v in codes.items() if c >= 500) < 0.05 * sum(codes.values())


def test_tsdb_streams_never_collide_on_dimensions():
    dims = json.loads((TEMPL / "infra_dims.json").read_text())
    registry.load_all()
    for g in gens():
        k = key(g)
        if k not in dims or k == "mysql/replica_status":  # replica dims are set by the pipeline from the raw sql.* metrics
            continue
        seen = set()
        n = 0
        for _, d in engine.generate(g, T0, T0 + timedelta(hours=1)):
            n += 1
            sig = (d["@timestamp"],) + tuple(json.dumps(get(d, f), sort_keys=True) for f in dims[k] if not f.startswith(("cloud.", "container.")))
            assert sig not in seen, f"{k}: two documents share dimensions and timestamp"
            seen.add(sig)
        assert n > 0


def test_otel_metric_series_do_not_collide():
    for k in ("redis_otel/metrics-redisreceiver.otel", "mysql_otel/metrics-mysqlreceiver.otel", "kafka_otel/metrics-kafkametricsreceiver.otel", "nginx_otel/metrics-nginxreceiver.otel",
              "redisenterprise_otel/metrics-redisenterprise.otel"):
        seen = set()
        for d in docs_of(k, 1):
            sig = (d["@timestamp"], d["_metric_names_hash"], json.dumps(d.get("attributes"), sort_keys=True), json.dumps(d["resource"]["attributes"], sort_keys=True))
            assert sig not in seen, k
            seen.add(sig)


def test_tsdb_bulk_has_no_id_and_logs_keep_the_id_and_dynamic_templates_move_to_the_action():
    assert engine.is_tsdb("metrics-redisreceiver.otel-synthetic") and engine.is_tsdb("metrics-kafka.broker-default") and engine.is_tsdb("metrics-nginx.stubstatus-default")
    assert not engine.is_tsdb("logs-nginx.access-default") and not engine.is_tsdb("metrics-windows.perfmon-default") and not engine.is_tsdb("logs-nginx.access.otel-synthetic")
    d = docs_of("redis_otel/metrics-redisreceiver.otel", 1)[0]
    assert "_dynamic_templates" in d and d["_dynamic_templates"]["metrics.redis.connections.received"] == "counter_long"
    lines = engine.bulk_lines("metrics-redisreceiver.otel-synthetic", [("abc", dict(d))])
    assert "_id" not in lines[0]["create"] and lines[0]["create"]["dynamic_templates"]["metrics.redis.memory.used"] == "gauge_long"
    assert "_dynamic_templates" not in lines[1]
    nl = engine.bulk_lines("logs-nginx.access-default", [("abc", {"message": "x"})])
    assert nl[0]["create"] == {"_index": "logs-nginx.access-default", "_id": "abc"}


def test_otel_counters_are_monotonic_per_series():
    per: dict = {}
    for d in sorted(docs_of("mysql_otel/metrics-mysqlreceiver.otel", 12), key=lambda x: x["@timestamp"]):
        attrs = json.dumps(d.get("attributes"), sort_keys=True)
        for m, v in d["metrics"].items():
            if d["_dynamic_templates"][f"metrics.{m}"].startswith("counter"):
                per.setdefault((d["resource"]["attributes"]["host.name"], attrs, m), []).append(v)
    assert per
    for k, vals in per.items():
        assert vals == sorted(vals), k


@pytest.mark.timeout(240)  # generates a full 7 day backfill; slow on shared CI runners
def test_volume_budget_per_tick_and_backfill():
    week = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
    total = sum(1 for g in gens() for _ in engine.generate(g, week, week + timedelta(days=7)))
    assert total < 320_000, total  # about 300k documents for a 7 day backfill
    peak = datetime(2026, 10, 5, 5, 30, tzinfo=UTC)
    n = sum(1 for g in gens() for _ in engine.generate(g, peak, peak + timedelta(minutes=5)))
    assert n < 400, n  # per 5 minute tick at the busiest time of day
    assert total / (7 * 288) < 200


def test_every_metric_stream_is_fresh_every_ten_minutes_even_at_night():
    night = datetime(2026, 10, 6, 19, 0, tzinfo=UTC)
    for g in gens():
        if g.stream.type != "metrics" or key(g) == "windows/perfmon" or key(g) == "mysql/galera_status":
            continue
        ds = [d for _, d in engine.generate(g, night, night + timedelta(minutes=11))]
        assert ds, key(g)


def test_replay_gives_only_conflicts_and_tick_reports_no_errors():
    from tests.test_feeder_core import FakeClient  # same stand-in as the core tests

    class TsdbAwareClient(FakeClient):
        """TSDB bulk actions carry no _id: ES derives it from dimensions + timestamp, so a repeated document is a 409."""

        def bulk(self, lines):
            fixed = []
            for i in range(0, len(lines), 2):
                meta = dict(lines[i]["create"])
                if "_id" not in meta:
                    meta["_id"] = json.dumps(lines[i + 1], sort_keys=True, default=str)
                fixed += [{"create": meta}, lines[i + 1]]
            return super().bulk(fixed)

    c = TsdbAwareClient()
    sel = [g for g in gens() if key(g) in ("nginx/access", "kafka/broker", "redis_otel/metrics-redisreceiver.otel")]
    now = T0 + timedelta(minutes=30)
    r1 = engine.tick(c, sel, now, 30)
    assert r1["created"] > 0 and r1["errors"] == 0
    for k in list(c.state):
        c.state[k]["last_covered"] = profile_iso(T0)
    r2 = engine.tick(c, sel, now, 30)
    assert r2["created"] == 0 and r2["errors"] == 0


def profile_iso(ts):
    from feeder import profile
    return profile.iso(ts)


def test_coverage_converts_legacy_match_type_phrase_filters():
    f = {"meta": {"key": "metricset.name"}, "query": {"match": {"metricset.name": {"query": "service", "type": "phrase"}}}}
    assert coverage.filter_to_query(f) == {"match_phrase": {"metricset.name": "service"}}
    g = {"meta": {}, "query": {"match_phrase": {"a": "b"}}}
    assert coverage.filter_to_query(g) == {"match_phrase": {"a": "b"}}
