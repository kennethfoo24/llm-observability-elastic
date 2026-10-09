"""Offline tests of the REST feeder group (stage 4a): panw, cisco_asa, cisco_meraki, netflow, postgresql (+ OTel) and system."""
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from feeder import catalog, engine, profile, registry
from feeder.gen import rest_panw, rest_postgres, rest_system

UTC = timezone.utc
T0 = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)  # Monday 11:00 Singapore


def gens():
    return registry.generators("rest")


def key(g):
    return g.stream.key


def docs_of(k, hours=3, start=T0):
    g = next(x for x in gens() if key(x) == k)
    return [d for _, d in engine.generate(g, start, start + timedelta(hours=hours))]


def get(d, path):
    parts = path.split(".")
    cur = d
    for i, p in enumerate(parts):
        if not isinstance(cur, dict):
            return None
        if p in cur:
            cur = cur[p]
            continue
        return cur.get(".".join(parts[i:]))
    return cur


def test_catalog_covers_every_package_of_the_group():
    registry.load_all()
    names = {p.name for p in catalog.packages("rest")}
    assert names == {"panw", "cisco_asa", "cisco_meraki", "netflow", "postgresql", "postgresql_otel", "system", "system_otel"}
    keys = [key(g) for g in gens()]
    assert len(keys) == len(set(keys)), "state keys must be unique per stream"
    assert {"panw/panos", "cisco_asa/log", "cisco_meraki/log", "netflow/log", "postgresql/log", "system/auth", "system/security", "system/memory"} <= set(keys)


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
        if g.stream.dataset.endswith(".otel"):
            ra = d["resource"]["attributes"]
            assert ra["tags"] == ["synthetic", "synthetic-data-feeder"] and ra["labels.synthetic"] == "true"
            assert d["data_stream"]["namespace"] == "synthetic"


REQUIRED = {
    "panw/panos": ["message", "observer.serial_number"], "cisco_asa/log": ["message"], "cisco_meraki/log": ["message"],
    "netflow/log": ["netflow.vlan_id", "netflow.source_ipv4_address", "netflow.destination_ipv4_address", "source.ip", "destination.ip", "network.bytes", "network.transport"],
    "postgresql/log": ["message", "host.name"], "system/auth": ["message", "host.name"],
    "system/security": ["winlog.event_id", "winlog.provider_name", "winlog.channel", "event.code", "winlog.event_data"],
    "system/memory": ["system.memory.swap.total", "system.memory.swap.used.pct", "system.memory.total", "host.name"],
    "postgresql_otel/metrics-postgresqlreceiver.otel": ["metrics", "_metric_names_hash", "resource.attributes.service.instance.id"],
    "postgresql_otel/logs-postgresqlreceiver.otel": ["event_name", "attributes.db.query.text", "attributes.db.namespace"],
}


@pytest.mark.parametrize("k", sorted(REQUIRED))
def test_required_fields_per_stream(k):
    ds = docs_of(k)
    assert ds, k
    for d in ds[:80]:
        for f in REQUIRED[k]:
            assert get(d, f) not in (None, ""), (k, f)


# --- Palo Alto -------------------------------------------------------------------------------------------------------------
def _csv_row(msg: str) -> list[str]:
    head = msg.split(",", 7)  # blank, received, serial, type, subtype, config version, generated, rest
    assert len(head) == 8
    return list(csv.reader(io.StringIO(head[7])))[0]


def test_panw_lines_have_the_exact_column_count_of_every_log_type():
    seen = Counter()
    for d in docs_of("panw/panos", 24):
        msg = d["message"]
        typ = msg.split(",")[3]
        kind = {"TRAFFIC": "traffic", "THREAT": "threat", "DECRYPTION": "decryption", "GLOBALPROTECT": "globalprotect", "SYSTEM": "system", "CONFIG": "config",
                "USERID": "userid", "IPTAG": "ip_tag", "AUTHENTICATION": "authentication", "HIP-MATCH": "hipmatch", "CORRELATION": "correlated_event",
                "START": "tunnel_inspection", "END": "tunnel_inspection", "GTP": "gtp", "SCTP": "sctp"}[typ]
        assert len(_csv_row(msg)) == len(rest_panw.FIELDS[kind]), typ
        seen[typ] += 1
        assert re.match(r"^1,\d{4}/\d\d/\d\d \d\d:\d\d:\d\d,\d{12},", msg)
    assert set(seen) >= {"TRAFFIC", "THREAT", "DECRYPTION", "GLOBALPROTECT", "SYSTEM", "CONFIG", "USERID", "IPTAG", "AUTHENTICATION", "HIP-MATCH", "CORRELATION",
                         "GTP", "SCTP"}, seen
    assert {"START", "END"} & set(seen)


def test_panw_fills_the_application_columns_the_dashboards_need():
    sample = next(d for d in docs_of("panw/panos", 12) if d["message"].split(",")[3] == "TRAFFIC")
    cols = dict(zip(rest_panw.FIELDS["traffic"], _csv_row(sample["message"])))
    for f in ("panw.panos.application.category", "panw.panos.application.risk_level", "panw.panos.application.technology"):
        assert cols[f]
    assert cols["panw.panos.application.risk_level"] in {"1", "2", "3", "4", "5"}


# --- Cisco, NetFlow, PostgreSQL logs, auth ------------------------------------------------------------------------------------
def test_cisco_lines_look_like_the_real_sources():
    for d in docs_of("cisco_asa/log", 3)[:40]:
        assert re.search(r"%ASA-\d-\d{6}: ", d["message"])
    ms = [d["message"] for d in docs_of("cisco_meraki/log", 24)]
    kinds = {m_.group(1) for m in ms if (m_ := re.search(r"airmarshal_events type=(\w+)", m))}
    assert kinds == {"rogue_ssid_detected", "ssid_spoofing_detected"}
    assert all("wired_mac=" in m and "fc_type=" in m for m in ms if "airmarshal_events" in m)
    assert any(" ip_flow_start " in m for m in ms) and any(" ip_flow_end " in m for m in ms)


def test_netflow_uses_public_addresses_so_the_pipeline_can_enrich_geo_and_as():
    ds = docs_of("netflow/log", 6)
    pub = [d for d in ds if not d["source"]["ip"].startswith("10.") or not d["destination"]["ip"].startswith("10.")]
    assert len(pub) == len(ds)
    assert {d["netflow"]["vlan_id"] for d in ds} <= {10, 20, 30, 100, 200} and len({d["netflow"]["vlan_id"] for d in ds}) > 2
    assert all(d["network"]["bytes"] == d["netflow"]["octet_delta_count"] for d in ds)


def test_postgresql_log_lines_match_the_default_log_line_prefix():
    ds = docs_of("postgresql/log", 12)
    pat = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} UTC \[\d+\] (\S+@\S+ )?(LOG|ERROR|WARNING|FATAL):  ")
    assert all(pat.match(d["message"]) for d in ds)
    assert any("duration:" in d["message"] for d in ds) and any(" ERROR:" in d["message"] for d in ds)


def test_linux_auth_covers_useradd_groupadd_sudo_errors_and_ssh_methods():
    msgs = [d["message"] for d in docs_of("system/auth", 24)]
    assert any("useradd[" in m for m in msgs) and any("groupadd[" in m for m in msgs)
    assert any("NOT in sudoers" in m or "incorrect password" in m or "not allowed" in m for m in msgs)
    assert any("Accepted publickey" in m for m in msgs) and any("Accepted password" in m for m in msgs)
    assert all(d["input"]["type"] == "log" for d in docs_of("system/auth", 1))


# --- Windows Security ---------------------------------------------------------------------------------------------------------
DASHBOARD_CODES = {"4624", "4625", "4627", "4648", "4662", "4663", "4672", "4675", "4720", "4722", "4725", "4726", "4728", "4732", "4738", "4740", "4781",
                   "4793", "4798", "4800", "4801", "4931", "5058", "5059", "5061", "5136", "5447", "6416", "6419", "6420", "6421", "6422", "4945", "4962"}


def test_windows_security_events_carry_event_data_for_the_dashboard_codes():
    assert DASHBOARD_CODES <= set(rest_system.SPEC)
    ds = docs_of("system/security", 48)
    codes = Counter(d["event"]["code"] for d in ds)
    assert len(codes) > 40, len(codes)
    for d in ds[:200]:
        assert d["winlog"]["event_id"] == d["event"]["code"] and d["winlog"]["provider_name"] == "Microsoft-Windows-Security-Auditing"
        assert d["winlog"]["event_data"]
    logon = next(d for d in ds if d["event"]["code"] == "4624")
    assert logon["winlog"]["event_data"]["LogonType"] and logon["winlog"]["event_data"]["IpAddress"]
    assert next(d for d in ds if d["event"]["code"] == "4625")["event"]["outcome"] == "failure"


def test_swap_usage_is_present_and_consistent():
    for d in docs_of("system/memory", 2)[:40]:
        sw = d["system"]["memory"]["swap"]
        assert sw["total"] > 0 and 0 <= sw["used"]["pct"] <= 1
        assert sw["used"]["bytes"] + sw["free"] == sw["total"]


# --- OTel PostgreSQL ----------------------------------------------------------------------------------------------------------
PGK = "postgresql_otel/metrics-postgresqlreceiver.otel"


def test_postgres_otel_series_do_not_collide_and_counters_are_monotonic():
    seen = set()
    per: dict = {}
    for d in sorted(docs_of(PGK, 12), key=lambda x: x["@timestamp"]):
        sig = (d["@timestamp"], d["_metric_names_hash"], json.dumps(d.get("attributes"), sort_keys=True), json.dumps(d["resource"]["attributes"], sort_keys=True))
        assert sig not in seen
        seen.add(sig)
        for m, v in d["metrics"].items():
            if d["_dynamic_templates"][f"metrics.{m}"].startswith("counter"):
                per.setdefault((sig[2], sig[3], m), []).append(v)
    assert per
    for k, vals in per.items():
        assert vals == sorted(vals), k


def test_postgres_otel_emits_every_metric_the_dashboards_query():
    names = set()
    for d in docs_of(PGK, 3):
        names |= set(d["metrics"])
    need = {"postgresql.blks_hit", "postgresql.blks_read", "postgresql.deadlocks", "postgresql.temp_files", "postgresql.temp.io", "postgresql.rollbacks",
            "postgresql.commits", "postgresql.bgwriter.maxwritten", "postgresql.database.locks", "postgresql.tup_inserted", "postgresql.tup_updated",
            "postgresql.tup_deleted", "postgresql.tup_fetched", "postgresql.tup_returned", "postgresql.backends", "postgresql.connection.max"}
    assert need <= names, need - names
    ev = {d["event_name"] for d in docs_of("postgresql_otel/logs-postgresqlreceiver.otel", 6)}
    assert ev == {"db.server.query_sample", "db.server.top_query"}


def test_postgres_otel_hit_ratio_is_high_and_counters_have_the_real_mapping_kinds():
    d = next(x for x in docs_of(PGK, 1) if "postgresql.blks_hit" in x["metrics"])
    assert d["metrics"]["postgresql.blks_hit"] > 20 * d["metrics"]["postgresql.blks_read"]
    assert d["_dynamic_templates"]["metrics.postgresql.blks_hit"] == "counter_long" and d["_dynamic_templates"]["metrics.postgresql.backends"] == "gauge_long"
    assert engine.is_tsdb("metrics-postgresqlreceiver.otel-synthetic") and engine.is_tsdb("metrics-system.memory-default")
    assert not engine.is_tsdb("logs-postgresqlreceiver.otel-synthetic")


# --- volume and idempotency ---------------------------------------------------------------------------------------------------
@pytest.mark.timeout(240)  # generates a full 7 day backfill; slow on shared CI runners
def test_volume_budget_per_tick_and_backfill():
    week = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
    total = sum(1 for g in gens() for _ in engine.generate(g, week, week + timedelta(days=7)))
    assert total < 400_000, total
    peak = datetime(2026, 10, 5, 5, 30, tzinfo=UTC)
    n = sum(1 for g in gens() for _ in engine.generate(g, peak, peak + timedelta(minutes=5)))
    assert n < 400, n


def test_replay_gives_only_conflicts_and_tick_reports_no_errors():
    from tests.test_feeder_core import FakeClient

    class TsdbAwareClient(FakeClient):
        def bulk(self, lines):
            fixed = []
            for i in range(0, len(lines), 2):
                meta = dict(lines[i]["create"])
                if "_id" not in meta:
                    meta["_id"] = json.dumps(lines[i + 1], sort_keys=True, default=str)
                fixed += [{"create": meta}, lines[i + 1]]
            return super().bulk(fixed)

    c = TsdbAwareClient()
    sel = [g for g in gens() if key(g) in ("panw/panos", "system/memory", PGK, "netflow/log")]
    now = T0 + timedelta(minutes=30)
    r1 = engine.tick(c, sel, now, 30)
    assert r1["created"] > 0 and r1["errors"] == 0
    for k in list(c.state):
        c.state[k]["last_covered"] = profile.iso(T0)
    r2 = engine.tick(c, sel, now, 30)
    assert r2["created"] == 0 and r2["errors"] == 0
