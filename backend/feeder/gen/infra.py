"""Stage 2 generators: INFRASTRUCTURE (nginx, windows, redis, mysql, kafka). Shared catalog, topology and helpers.

Modules: infra.py (this: catalog, topology, helpers), infra_nginx.py, infra_windows.py, infra_redis.py, infra_mysql.py,
infra_kafka.py, infra_otel.py (the OpenTelemetry shaped data streams of the *_otel packages).
"""
from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import catalog, engine, profile
from ..harvest import load_template
from ..registry import Ctx

GROUP = "infra"

# ----- catalog ---------------------------------------------------------------------------------------------------------
catalog.register(
    catalog.pkg("nginx", "3.2.2", GROUP, [("access", "nginx.access", "logs"), ("error", "nginx.error", "logs"),
                                           ("stubstatus", "nginx.stubstatus", "metrics")]),
    catalog.pkg("nginx_ingress_controller", "1.14.2", GROUP, [("access", "nginx_ingress_controller.access", "logs"),
                                                              ("error", "nginx_ingress_controller.error", "logs")]),
    catalog.pkg("windows", "3.10.0", GROUP, [
        ("applocker_exe_and_dll", "windows.applocker_exe_and_dll", "logs"), ("applocker_msi_and_script", "windows.applocker_msi_and_script", "logs"),
        ("applocker_packaged_app_deployment", "windows.applocker_packaged_app_deployment", "logs"),
        ("applocker_packaged_app_execution", "windows.applocker_packaged_app_execution", "logs"),
        ("forwarded", "windows.forwarded", "logs"), ("perfmon", "windows.perfmon", "metrics"), ("powershell", "windows.powershell", "logs"),
        ("powershell_operational", "windows.powershell_operational", "logs"), ("service", "windows.service", "metrics"),
        ("sysmon_operational", "windows.sysmon_operational", "logs"), ("windows_defender", "windows.windows_defender", "logs")]),
    catalog.pkg("redis", "1.21.2", GROUP, [("info", "redis.info", "metrics"), ("key", "redis.key", "metrics"), ("keyspace", "redis.keyspace", "metrics"),
                                           ("log", "redis.log", "logs"), ("slowlog", "redis.slowlog", "logs")]),
    catalog.pkg("redisenterprise", "0.12.2", GROUP, [("node", "redisenterprise.node", "metrics"), ("proxy", "redisenterprise.proxy", "metrics")]),
    catalog.pkg("mysql", "1.31.0", GROUP, [("error", "mysql.error", "logs"), ("galera_status", "mysql.galera_status", "metrics"),
                                           ("performance", "mysql.performance", "metrics"), ("replica_status", "mysql.replica_status", "metrics"),
                                           ("slowlog", "mysql.slowlog", "logs"), ("status", "mysql.status", "metrics")]),
    catalog.pkg("kafka", "1.27.2", GROUP, [(d, f"kafka.{d}", "metrics") for d in (
        "broker", "consumer", "consumergroup", "controller", "jvm", "log_manager", "network", "partition", "producer", "raft",
        "replica_manager", "topic")] + [("log", "kafka.log", "logs")]),
    catalog.pkg("kafka_connect", "0.1.2", GROUP, [(d, f"kafka_connect.{d}", "metrics") for d in ("client", "connector", "task", "worker")]),
    # OpenTelemetry content packages: assets only; their data streams are the OTel ones in infra_otel.py
    *[catalog.pkg(n, v, GROUP, []) for n, v in [("nginx_otel", "0.6.1"), ("nginx_ingress_controller_otel", "0.4.1"), ("redis_otel", "0.3.2"),
                                                ("redisenterprise_otel", "0.3.2"), ("mysql_otel", "0.6.1"), ("kafka_otel", "0.3.1")]],
)
S = {s.key: s for s in catalog.streams(GROUP)}

# Integration metric streams are TSDB data streams (probed on the live project): custom _id is refused, repeats give 409 on the
# derived _id, and every document needs distinct dimensions per timestamp. windows.perfmon is the only plain metrics stream.
TSDB_STREAMS = [k for k, s in S.items() if s.type == "metrics" and k != "windows/perfmon"]
engine.NO_ID_PREFIXES.extend(f"metrics-{S[k].dataset}-" for k in TSDB_STREAMS)


@dataclass(frozen=True)
class OtelStream(catalog.Stream):
    """A data stream of an OTel content package. Written in its own namespace so the synthetic series never mix with
    real collector data that may already live in the `default` namespace of the same dataset."""
    namespace: str = "synthetic"
    no_pipeline = True  # documents are final OTel shaped: no package ingest pipeline to simulate

    @property
    def index(self) -> str:
        return f"{self.type}-{self.dataset}-{self.namespace}"


# ----- topology (one believable estate shared by every generator) ----------------------------------------------------------
NGINX_HOSTS = ["web-sin-01", "web-sin-02", "web-sin-03"]
WINDOWS_HOSTS = ["WIN-AD01", "WIN-FS01", "WIN-APP01", "WIN-SQL01", "WIN-WKS07"]
REDIS_NODES = [("redis-cache-01", "master"), ("redis-cache-02", "slave")]
MYSQL_NODES = [("mysql-primary-01", "primary"), ("mysql-replica-01", "replica"), ("mysql-replica-02", "replica")]
KAFKA_BROKERS = [1, 2, 3]
KAFKA_TOPICS = ["orders", "payments", "inventory", "shipments", "clicks", "page-views", "notifications", "audit-log",
                "user-events", "search-queries", "metrics-raw", "dead-letter"]
KAFKA_GROUPS = [("order-processor", ["orders", "payments"]), ("inventory-sync", ["inventory", "shipments"]),
                ("analytics-ingest", ["clicks", "page-views", "user-events", "search-queries"]),
                ("notifier", ["notifications"]), ("audit-writer", ["audit-log", "dead-letter"])]
DOMAIN = "corp.example.org"


# ----- helpers --------------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def tpl(key: str) -> dict:
    """The committed sample event of a stream (deep copies are the caller's job: use `sample`)."""
    return load_template(S[key])


def sample(key: str) -> dict:
    return json.loads(json.dumps(tpl(key)))


def J(o) -> str:
    return json.dumps(o, separators=(",", ":"))


def host_of(i: int, hosts: list[str]) -> str:
    return hosts[i % len(hosts)]


def stable(*parts: object) -> int:
    """Stable small integer from arbitrary parts (never Python hash()): for per host / per entity constants."""
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:4], "big")


def wave(ts: datetime, period_min: float, amp: float, phase: str = "") -> float:
    """Slow deterministic oscillation around 1.0 (for gauges that drift: memory, queue depth)."""
    import math
    p = (stable(phase) % 360) / 360 * 2 * math.pi
    return 1 + amp * math.sin(2 * math.pi * (ts.timestamp() / 60) / period_min + p)


ANCHOR = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()
STEP = 600
_CUM = [0.0]


def _cum(step: int) -> float:
    """Integral of the activity profile from ANCHOR to the start of 10 minute step `step` (cached, one pass)."""
    while len(_CUM) <= step:
        t = ANCHOR + (len(_CUM) - 1) * STEP
        _CUM.append(_CUM[-1] + profile.activity(datetime.fromtimestamp(t + STEP / 2, timezone.utc)) * STEP)
    return _CUM[step]


class LoadRate(float):
    """A per second rate that follows the activity profile: base + peak * load/1.5. As a float it is the instantaneous
    rate (for gauges); `counter` integrates it over time so counters stay monotonic while the load changes."""
    b: float
    p: float

    def __new__(cls, base: float, peak: float, load: float = 1.0):
        o = float.__new__(cls, base + peak * min(load, 1.5) / 1.5)
        o.b, o.p = base, peak
        return o

    def scaled(self, k: float) -> "LoadRate":
        o = float.__new__(LoadRate, float(self) * k)
        o.b, o.p = self.b * k, self.p * k
        return o

    def __mul__(self, k):  # type: ignore[override]
        return self.scaled(float(k))

    __rmul__ = __mul__


def load_counter(ts: datetime, rate: "LoadRate", key: str) -> int:
    t = ts.timestamp() - ANCHOR
    step = int(t // STEP)
    frac = (t - step * STEP) / STEP
    integ = _cum(step) + (_cum(step + 1) - _cum(step)) * frac  # activity-seconds, linearly interpolated: monotonic
    return int(stable(key) % 5_000_000 + rate.b * t + rate.p / 1.5 * integ)


def counter(ts: datetime, rate_per_s: float, key: str, load_aware: bool = True) -> int:
    """Monotonic counter value at ts: the integral of rate over time since an epoch (deterministic, no state).
    Works for streams that are written at arbitrary minute resolution: value(t2) >= value(t1).
    A LoadRate follows the activity profile (still monotonic)."""
    if isinstance(rate_per_s, LoadRate):
        return load_counter(ts, rate_per_s, key)
    t = ts.timestamp()
    base = 1_700_000_000
    avg = 0.55 if load_aware else 1.0  # average profile load, so counters grow at roughly rate * avg
    return int(stable(key) % 5_000_000 + (t - base) * rate_per_s * avg)


def doc_from(key: str, **over) -> dict:
    d = sample(key)
    d.update(over)
    return d


def merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def set_path(d: dict, path: str, value) -> dict:
    cur = d
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    return d


def otel_tag(doc: dict) -> dict:
    """OTel mappings have no top level `tags`/`labels`: carry the synthetic tag as a resource attribute (a TSDB
    dimension; the passthrough mapping exposes it as `tags` and `labels.synthetic`)."""
    ra = doc.setdefault("resource", {}).setdefault("attributes", {})
    ra["tags"] = ["synthetic", "synthetic-data-feeder"]
    ra["labels.synthetic"] = "true"
    return doc


def sget(c: Ctx, *parts):
    return profile.rng_for(c.stream.key, *parts)


def _mac(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return "-".join(h[i:i + 2] for i in (0, 2, 4, 6, 8, 10)).upper()


def host_block(name: str, kind: str = "linux", idx: int = 0) -> dict:
    """ECS host fields for a topology host (stable per name)."""
    h = hashlib.sha256(name.encode()).hexdigest()
    ip = f"10.20.{stable(name) % 200 + 1}.{stable(name, 'ip') % 200 + 10}"
    if kind == "windows":
        os_ = {"family": "windows", "kernel": "10.0.20348.2700 (WinBuild.160101.0800)", "name": "Windows Server 2022 Datacenter",
               "platform": "windows", "type": "windows", "version": "10.0"}
        arch = "x86_64"
    else:
        os_ = {"codename": "jammy", "family": "debian", "kernel": "5.15.0-122-generic", "name": "Ubuntu", "platform": "ubuntu",
               "type": "linux", "version": "22.04.5 LTS (Jammy Jellyfish)"}
        arch = "x86_64"
    return {"architecture": arch, "containerized": False, "hostname": name.lower() if kind == "windows" else name, "id": h[:32],
            "ip": [ip], "mac": [_mac(name)], "name": name, "os": os_}


def agent_block(name: str, kind: str = "filebeat") -> dict:
    h = hashlib.sha256(("agent" + name).encode()).hexdigest()
    aid = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    return {"ephemeral_id": aid[::-1], "id": aid, "name": name, "type": kind, "version": "9.2.0"}


def log_base(host: str, path: str, kind: str = "linux") -> dict:
    """Envelope a log shipper adds around the raw line (the package pipeline parses `message`)."""
    return {"host": host_block(host, kind), "agent": agent_block(host), "input": {"type": "log"}, "log": {"file": {"path": path}},
            "ecs": {"version": "8.17.0"}}


def metric_base(key: str, host: str, kind: str = "linux", module: str | None = None) -> dict:
    """Template (sample event) re-hosted on a topology host: keeps the package's own structure, drops the sample's data."""
    d = sample(key)
    d["host"] = host_block(host, kind)
    d["agent"] = agent_block(host, "metricbeat")
    d.setdefault("event", {})
    d["event"].pop("ingested", None)
    if module and not d["event"].get("module"):  # constant_keyword event.module: keep the sample's (e.g. kafka JMX streams use jolokia)
        d["event"]["module"] = module
    d.pop("cloud", None)
    d.get("data_stream", {}).pop("namespace", None)
    return d


# ----- field-driven metric filling -----------------------------------------------------------------------------------------
_ZEROISH = ("error", "fail", "unclean", "offline", "dead", "under_min", "under_replicated", "reject", "expired", "retry", "dropped",
            "killed", "unknown", "throttle", "timeout", "abort", "lost", "conflict", "denied")
_PCT = {"min": .3, "mean": 1.0, "avg": 1.0, "median": .9, "p50": .9, "p75": 1.3, "p95": 2.5, "p98": 3.2, "p99": 4.0, "p999": 8.0, "max": 12.0,
        "stddev": .4}


def fields_path(key: str):
    s = S[key]
    return s.template_path.with_name(s.dir + ".fields.json")


@functools.lru_cache(maxsize=None)
def spec(key: str) -> dict:
    """{field: type} of the package-owned fields of a stream (committed next to the template)."""
    p = fields_path(key)
    return json.loads(p.read_text()) if p.exists() else {}


def auto_value(path: str, ty: str, rng, ts: datetime, key: str, load: float, base: float = 1.0):
    """A plausible value from the field name and type. Counters grow monotonically (deterministic in time)."""
    n = path.lower()
    last = n.rsplit(".", 1)[-1]
    if ty == "boolean":
        return True
    if ty not in ("long", "integer", "short", "double", "float", "scaled_float"):
        return None
    is_int = ty in ("long", "integer", "short")
    if any(z in n for z in _ZEROISH):
        v = 0 if rng.random() > 0.08 else rng.randint(1, 3)
    elif last in _PCT:
        b = max(0.2, base) * (0.7 + 0.8 * min(load, 1.5) / 1.5) * rng.lognormvariate(0, 0.25)
        v = b * _PCT[last]
    elif "percent" in n or "pct" in n or "usage" in last and "heap" not in n:
        v = rng.uniform(5, 70) * (0.5 + load / 3)
        v = min(v, 99.0)
    elif "idle" in n and ("ratio" in n or "percent" in n):
        v = rng.uniform(0.6, 0.98)
    elif "ratio" in n:
        v = rng.uniform(0.01, 0.99)
    elif any(w in n for w in ("count", "total", "num_", "number", "_sum", "records", "requests")) and "per_sec" not in n and "rate" not in n:
        v = counter(ts, 2.0 * base, key + path) if is_int else counter(ts, 2.0 * base, key + path) * 1.0
    elif "rate" in n or "per_sec" in n or "per_second" in n:
        v = rng.uniform(0.2, 6.0) * base * (0.3 + load)
    elif "bytes" in n or "size" in n or "memory" in n:
        v = rng.uniform(2e5, 5e6) * base * (0.5 + load)
    elif "ms" in last or "time" in n or "latency" in n or "duration" in n:
        v = rng.lognormvariate(1.5, 0.6) * base
    elif n.endswith(".id") or last.endswith("_id"):
        v = 1
    else:
        v = rng.uniform(1, 20) * base
    return int(v) if is_int else round(float(v), 4)


def fill(doc: dict, key: str, c: Ctx, base: float = 1.0, only: tuple[str, ...] | None = None, skip: tuple[str, ...] = (),
         ctr_key: str = "", zeros: bool = False) -> dict:
    """Set every numeric/boolean package field of the stream that is not already present in `doc`
    (`zeros=True`: also replace sample values that are 0, so sample-shaped docs do not stay flat)."""
    for path, ty in spec(key).items():
        if only is not None and not path.startswith(only):
            continue
        if any(s in path for s in skip) or "metric_fingerprint" in path:
            continue
        cur = doc
        parts = path.split(".")
        ok = True
        for p in parts[:-1]:
            nxt = cur.get(p)
            if nxt is None:
                nxt = cur[p] = {}
            if not isinstance(nxt, dict):
                ok = False
                break
            cur = nxt
        if not ok or (parts[-1] in cur and not (zeros and cur[parts[-1]] == 0 and not isinstance(cur[parts[-1]], bool))):
            continue
        v = auto_value(path, ty, c.rng, c.ts, key + ctr_key, c.load, base)
        if v is not None:
            cur[parts[-1]] = v
    return doc
