"""OpenTelemetry shaped data for the *_otel content packages: nginx_otel, nginx_ingress_controller_otel, redis_otel,
redisenterprise_otel, mysql_otel and kafka_otel.

What the dashboards read (checked with `coverage`): metrics-<receiver>.otel-* with `data_stream.dataset == <receiver>.otel`
(redisenterprise: exactly metrics-redisenterprise.otel-default), logs-* for the nginx and MySQL log based panels.

Direct writes into the OTel data streams work (probed on the live project) with three rules the generators follow:
  * metrics streams are TSDB: no custom _id (the engine omits it; repeats answer 409 on the derived _id),
  * documents are shaped like the Elastic OTLP endpoint output: `metrics.<name>`, `attributes`, `resource.attributes`,
    `scope`, `_metric_names_hash`, and counter/gauge mapping hints (`_dynamic_templates`, applied by the engine on the bulk action),
  * the OTel mappings have no top level `tags`: the tag lives in resource.attributes (`tags`, `labels.synthetic`) and the passthrough
    mapping exposes it as `tags: synthetic` and `labels.synthetic: true`, so the usual KQL filter works.
Series are written to the `synthetic` namespace (metrics-<receiver>.otel-synthetic) so they never mix with real collector data.
"""
from __future__ import annotations

import functools
import hashlib
import json
from datetime import datetime
from pathlib import Path

from .. import catalog, profile, registry
from ..registry import Ctx, Generator
from . import infra
from .infra import GROUP, KAFKA_BROKERS, KAFKA_GROUPS, KAFKA_TOPICS, MYSQL_NODES, NGINX_HOSTS, OtelStream, REDIS_NODES

KINDS: dict[str, str] = json.loads((Path(__file__).resolve().parent.parent / "templates" / "otel_metric_kinds.json").read_text())
SCOPE_VERSION = "9.5.0"


def stream(package: str, version: str, dataset: str, type_: str, namespace: str = "synthetic") -> OtelStream:
    return OtelStream(package, version, f"{type_}-{dataset}", dataset, type_, GROUP, namespace)


def scope(receiver: str, version: str = SCOPE_VERSION) -> dict:
    return {"name": f"github.com/open-telemetry/opentelemetry-collector-contrib/receiver/{receiver}", "version": version}


def metric_doc(s: OtelStream, ts: datetime, resource: dict, scope_: dict, attrs: dict | None, metrics: dict, kinds: dict | None = None) -> dict:
    """One OTLP data point group as the ES OTLP endpoint stores it. `kinds` overrides: name -> gl/gd/cl/cd."""
    names = sorted(metrics)
    dyn = {}
    for n in names:
        k = (kinds or {}).get(n) or KINDS.get(n)
        if k is None:
            k = "g" + ("d" if isinstance(metrics[n], float) else "l")
        dyn[f"metrics.{n}"] = {"gl": "gauge_long", "gd": "gauge_double", "cl": "counter_long", "cd": "counter_double"}[k]
        if k.endswith("l"):
            metrics[n] = int(metrics[n])
        else:
            metrics[n] = float(metrics[n])
    doc = {"@timestamp": profile.iso(ts), "_metric_names_hash": hashlib.sha1(",".join(names).encode()).hexdigest()[:8],  # noqa: S324
           "data_stream": {"type": "metrics", "dataset": s.dataset, "namespace": s.namespace}, "metrics": metrics,
           "resource": {"attributes": dict(resource)}, "scope": scope_, "start_timestamp": profile.iso(ts.replace(hour=0, minute=0, second=0)),
           "_dynamic_templates": dyn}
    if attrs:
        doc["attributes"] = attrs
    return infra.otel_tag(doc)


def log_doc(s: OtelStream, ts: datetime, resource: dict, scope_: dict, attrs: dict | None = None, body: dict | str | None = None, sev: str = "INFO", event_name: str | None = None) -> dict:
    sevn = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}[sev]
    doc = {"@timestamp": profile.iso(ts), "observed_timestamp": profile.iso(ts), "severity_text": sev, "severity_number": sevn,
           "data_stream": {"type": "logs", "dataset": s.dataset, "namespace": s.namespace}, "resource": {"attributes": dict(resource)}, "scope": scope_}
    if attrs:
        doc["attributes"] = attrs
    if isinstance(body, dict):
        doc["body"] = {"structured": body}
    elif body:
        doc["body"] = {"text": body}
    if event_name:
        doc["event_name"] = event_name
    return infra.otel_tag(doc)  # the generic logs OTel mapping has no top level tags either: tag via resource attributes (passthrough)


def host_res(host: str, service: str, extra: dict | None = None) -> dict:
    r = {"host.name": host, "host.id": hashlib.sha1(host.encode()).hexdigest()[:16], "os.type": "linux", "service.name": service, "service.instance.id": f"{host}:{service}"}  # noqa: S324
    if extra:
        r.update(extra)
    return r


# =============================== NGINX (nginxreceiver metrics, access and error logs) ==================================
OT_NGINX_HOSTS = NGINX_HOSTS[:2]
NGX_M = stream("nginx_otel", "0.6.1", "nginxreceiver.otel", "metrics")
NGX_A = stream("nginx_otel", "0.6.1", "nginx.access.otel", "logs")
NGX_E = stream("nginx_otel", "0.6.1", "nginx.error.otel", "logs")
ING_A = stream("nginx_ingress_controller_otel", "0.4.1", "nginx_ingress_controller.access.otel", "logs")
ING_E = stream("nginx_ingress_controller_otel", "0.4.1", "nginx_ingress_controller.error.otel", "logs")
NGINX_STATES = ["active", "reading", "writing", "waiting"]


def _ngx_metrics(c: Ctx) -> dict:
    host = OT_NGINX_HOSTS[c.i % len(OT_NGINX_HOSTS)]
    k = c.i // len(OT_NGINX_HOSTS)  # 0 = totals, 1..4 = connection states
    res = host_res(host, "nginx", {"nginx.version": "1.27.2"})
    sc = scope("nginxreceiver")
    r = c.rng
    if k == 0:
        reqs = infra.counter(c.ts, 3.0 + c.i, "otel-ngx-req" + host, False)
        acc = int(reqs * 0.55)
        return metric_doc(NGX_M, c.ts, res, sc, None, {"nginx.connections_accepted": acc, "nginx.connections_handled": acc, "nginx.requests": reqs})
    st = NGINX_STATES[k - 1]
    active = int(14 + 70 * min(c.load, 1.5) / 1.5 + r.randint(0, 5))
    val = {"active": active, "reading": r.randint(0, 3), "writing": max(1, int(active * 0.25)), "waiting": max(1, int(active * 0.7))}[st]
    return metric_doc(NGX_M, c.ts, res, sc, {"state": st}, {"nginx.connections_current": val})


def _ngx_access(c: Ctx) -> dict:
    from . import infra_nginx as ng
    r = c.rng
    host = r.choice(OT_NGINX_HOSTS)
    path = profile.pick(r, ng.PATHS)
    status = int(profile.pick(r, [(str(k), w) for k, w in ng.STATUS]))
    method = "POST" if path.startswith(("/api/v1/orders", "/api/v1/payments")) and r.random() < 0.5 else "GET"
    ua = profile.pick(r, ng.UAS)
    ip = r.choice(ng.CLIENT_IPS)
    uname = ua.split("/")[0] if not ua.startswith("Mozilla") else ("Chrome" if "Chrome" in ua else "Safari" if "Safari" in ua else "Firefox")
    size = 0 if status in (304, 301, 302) else int(r.lognormvariate(7.0, 1.0))
    attrs = {"http.request.method": method, "http.response.status_code": status, "http.version": "1.1", "source.address": ip, "url.original": path,
             "user_agent.name": uname, "user_agent.original": ua, "http.response.body.size": size, "log.level": "info"}
    body = f'{ip} - - [{ng.nginx_time(c.ts)}] "{method} {path} HTTP/1.1" {status} {size} "-" "{ua}"'
    return log_doc(NGX_A, c.ts, host_res(host, "nginx"), scope("filelogreceiver", "0.152.0"), attrs, body, "INFO" if status < 500 else "ERROR")


def _ngx_error(c: Ctx) -> dict:
    r = c.rng
    host = r.choice(OT_NGINX_HOSTS)
    lvl = r.choices(["error", "warn", "notice"], weights=[5, 4, 1])[0]
    msgs = ["upstream timed out (110: Connection timed out) while reading response header from upstream", "connect() failed (111: Connection refused) while connecting to upstream",
            "an upstream response is buffered to a temporary file /var/cache/nginx/proxy_temp/3/04/0000000043", "client intended to send too large body: 2097200 bytes",
            "open() \"/usr/share/nginx/html/wp-login.php\" failed (2: No such file or directory)"]
    attrs = {"log.level": lvl, "process.pid": 1000 + infra.stable(host) % 50, "thread.id": r.randrange(1, 4)}
    return log_doc(NGX_E, c.ts, host_res(host, "nginx"), scope("filelogreceiver", "0.152.0"), attrs, r.choice(msgs), {"error": "ERROR", "warn": "WARN", "notice": "INFO"}[lvl])


def _ing_access(c: Ctx) -> dict:
    from . import infra_nginx as ng
    r = c.rng
    up = profile.pick(r, [(n, w) for n, w, _ in ng.UPSTREAMS])
    path = profile.pick(r, ng.PATHS)
    status = int(profile.pick(r, [(str(k), w) for k, w in ng.STATUS]))
    ua = profile.pick(r, ng.UAS)
    uname = ua.split("/")[0] if not ua.startswith("Mozilla") else "Chrome" if "Chrome" in ua else "Safari" if "Safari" in ua else "Firefox"
    size = 0 if status in (304, 301, 302) else int(r.lognormvariate(6.8, 0.9))
    body = {"http": {"request": {"method": "GET", "time": round(r.lognormvariate(-4.0, 0.7), 3)}, "response": {"status_code": status, "body": {"size": size}}}, "source": {"address": r.choice(ng.CLIENT_IPS)},
            "upstream": {"name": f"default-{up}", "response": {"size": size, "status_code": status, "time": round(r.lognormvariate(-4.3, 0.7), 3)}}, "url": {"original": path, "path": path.split("?")[0]},
            "user_agent": {"name": uname, "original": ua}, "log": {"level": "info"}}
    return log_doc(ING_A, c.ts, host_res(ng.ING_HOST, "ingress-nginx-controller", {"k8s.namespace.name": "ingress-nginx", "k8s.pod.name": ng.ING_HOST}), scope("filelogreceiver", "0.152.0"), None, body, "INFO")


def _ing_error(c: Ctx) -> dict:
    from . import infra_nginx as ng
    r = c.rng
    lvl, f, ln, text = r.choice(ng.ING_ERRS)
    body = {"log": {"level": {"W": "warn", "E": "error", "I": "info"}[lvl]}, "source": {"file": {"name": f, "line_number": ln}}, "message": text, "thread": {"id": r.randrange(5, 12)}}
    return log_doc(ING_E, c.ts, host_res(ng.ING_HOST, "ingress-nginx-controller", {"k8s.namespace.name": "ingress-nginx", "k8s.pod.name": ng.ING_HOST}), scope("filelogreceiver", "0.152.0"), None, body,
                   {"W": "WARN", "E": "ERROR", "I": "INFO"}[lvl])


# =============================== REDIS (redisreceiver) ========================================================================
RED = stream("redis_otel", "0.3.2", "redisreceiver.otel", "metrics")


def _redis(c: Ctx) -> dict:
    node, role = REDIS_NODES[c.i % 2]
    k = c.i // 2  # 0 base, 1-2 cpu states, 3-4 databases
    res = host_res(node, "redis", {"redis.version": "7.4.1", "server.address": node, "server.port": "6379"})
    sc = scope("redisreceiver")
    r = c.rng
    mult = 1.0 if role == "master" else 0.45
    if k == 0:
        ops = infra.LoadRate(250 * mult, 2400 * mult, c.load)
        used = int((380e6 + 140e6 * infra.wave(c.ts, 240, 0.25, node)) * (1.0 if role == "master" else 0.95))
        proc = infra.counter(c.ts, ops * 0.6, node + "otel-cmd", False)
        hits = int(proc * 0.4)
        m = {"redis.clients.connected": int(40 + 220 * min(c.load, 1.5) / 1.5 * mult + r.randint(0, 6)), "redis.clients.blocked": r.choice([0, 1, 1, 2]),
             "redis.clients.max_input_buffer": 0, "redis.clients.max_output_buffer": 0, "redis.commands": ops, "redis.commands.processed": proc,
             "redis.connections.received": infra.counter(c.ts, 0.4 * mult, node + "otel-conn", False), "redis.connections.rejected": infra.counter(c.ts, 0.0004, node + "otel-rej", False) + (1 if r.random() < 0.0 else 0),
             "redis.keys.evicted": infra.counter(c.ts, 0.02, node + "otel-ev", False) if role == "master" else infra.counter(c.ts, 0.004, node + "otel-ev", False),
             "redis.keys.expired": infra.counter(c.ts, 2.5 * mult, node + "otel-ex", False), "redis.keyspace.hits": hits, "redis.keyspace.misses": int(hits * 0.14),
             "redis.latest_fork": 800 + r.randrange(0, 400), "redis.maxmemory": 1 << 30, "redis.memory.fragmentation_ratio": round(1.05 + 0.06 * r.random(), 2),
             "redis.memory.lua": 37888, "redis.memory.peak": int(max(used * 1.12, 520e6)), "redis.memory.rss": int(used * 1.1), "redis.memory.used": used,
             "redis.net.input": infra.counter(c.ts, ops * 55, node + "otel-ni", False), "redis.net.output": infra.counter(c.ts, ops * 210, node + "otel-no", False),
             "redis.rdb.changes_since_last_save": r.randrange(1, 4000), "redis.replication.backlog_first_byte_offset": infra.counter(c.ts, 1500, "otel-repl", False) - 1048576,
             "redis.replication.offset": infra.counter(c.ts, 1500, "otel-repl", False), "redis.slaves.connected": 1 if role == "master" else 0,
             "redis.uptime": int(c.ts.timestamp()) - 1_759_000_000 - infra.stable(node) % 1000}
        return metric_doc(RED, c.ts, res, sc, None, m)
    if k in (1, 2):
        st = ["sys", "user"][k - 1]
        return metric_doc(RED, c.ts, res, sc, {"state": st}, {"redis.cpu.time": infra.counter(c.ts, (0.04 if st == "sys" else 0.09) * mult, node + st, False) / 1000.0})
    db = str(k - 3)
    keys = int((42000 if db == "0" else 9000) * infra.wave(c.ts, 360, 0.08, node + db))
    return metric_doc(RED, c.ts, res, sc, {"db": db}, {"redis.db.avg_ttl": int(r.uniform(2.5e5, 9e5)), "redis.db.expires": int(keys * 0.8), "redis.db.keys": keys})


# =============================== REDIS ENTERPRISE (prometheus scrape, flat metric names) =====================================
REE = stream("redisenterprise_otel", "0.3.2", "redisenterprise.otel", "metrics", "default")  # dashboards read metrics-redisenterprise.otel-default
RE_NODES = ["rec-sin-1", "rec-sin-2", "rec-sin-3"]
RE_DBS = [("1", "orders-cache", 2), ("2", "session-store", 2)]
RE_RES = lambda node: {"service.name": "redis-enterprise", "service.instance.id": f"{node}:8070", "server.address": node, "server.port": "8070", "url.scheme": "https",  # noqa: E731
                       "host.name": node}


def _ree(c: Ctx) -> dict:
    r = c.rng
    i = c.i
    sc = {"name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/prometheusreceiver", "version": "0.152.0"}
    load = min(c.load, 1.5) / 1.5
    g = lambda **kw: {k: float(v) for k, v in kw.items()}  # noqa: E731
    gd = {}
    if i < 2:  # databases
        bdb, name, shards = RE_DBS[i]
        ops = (900 + 7000 * load) * (1.4 if i == 0 else 0.7) * r.uniform(0.92, 1.08)
        used = (1.6e9 + 0.5e9 * infra.wave(c.ts, 300, 0.2, name)) * (1 if i == 0 else 0.6)
        hits = ops * 55 * 0.88
        m = g(bdb_up=1, bdb_avg_latency=0.0006 + 0.0004 * load * r.uniform(0.8, 1.2), bdb_avg_latency_max=0.0021 + 0.003 * load, bdb_avg_read_latency=0.00055, bdb_avg_read_latency_max=0.0019,
              bdb_avg_write_latency=0.00078, bdb_avg_write_latency_max=0.0026, bdb_avg_other_latency=0.0005, bdb_avg_other_latency_max=0.0018, bdb_conns=40 + 190 * load, bdb_evicted_objects=r.randrange(0, 40),
              bdb_expired_objects=r.randrange(5, 400), bdb_ingress_bytes=ops * 140, bdb_egress_bytes=ops * 520, bdb_instantaneous_ops_per_sec=ops, bdb_mem_frag_ratio=1.1 + 0.05 * r.random(),
              bdb_memory_limit=4e9 if i == 0 else 2e9, bdb_no_of_keys=2.1e6 * (1 if i == 0 else 0.5), bdb_no_of_expires=1.4e6 * (1 if i == 0 else 0.5), bdb_read_hits=hits, bdb_read_misses=hits * 0.13,
              bdb_read_req=ops * 0.7, bdb_write_req=ops * 0.25, bdb_other_req=ops * 0.05, bdb_shard_cpu_system=0.04 * shards * load + 0.01, bdb_shard_cpu_user=0.11 * shards * load + 0.02,
              bdb_shards_used=shards, bdb_used_memory=used, shard_cpu=0.15 * load + 0.02)
        return metric_doc(REE, c.ts, RE_RES(RE_NODES[i]), sc, {"bdb": bdb}, m)
    i -= 2
    if i < 3:  # nodes
        node = RE_NODES[i]
        m = g(node_up=1, node_available_memory=9.5e9 - 1.2e9 * load, node_free_memory=9e9 - 1.5e9 * load + r.gauss(0, 5e7), node_cpu_user=0.1 + 0.2 * load, node_cpu_system=0.04 + 0.05 * load,
              node_cpu_idle=0.8 - 0.3 * load, node_cpu_iowait=0.004 + 0.01 * r.random(), node_conns=30 + 140 * load, node_total_req=900 + 6000 * load, node_egress_bytes=2e5 * (1 + load),
              node_ingress_bytes=6e4 * (1 + load), node_ephemeral_storage_avail=55e9 - 1e8 * i, node_persistent_storage_avail=190e9 - 2e8 * i, node_cur_aof_rewrites=float(r.random() < 0.05),
              node_status=1)
        m["node_cert_expiration_seconds"] = 86400 * (200 - i * 20) - c.ts.timestamp() % 86400
        return metric_doc(REE, c.ts, RE_RES(node), sc, {"node": str(i + 1), "path": "/etc/opt/redislabs/proxy_cert.pem"}, m)
    i -= 3
    if i < 4:  # shards (redis_* metrics)
        bdb, name, _ = RE_DBS[i // 2]
        role = "master" if i % 2 == 0 else "slave"
        node = RE_NODES[i % 3]
        ops = (450 + 3500 * load) * (1.0 if role == "master" else 0.5)
        used = (0.8e9 + 0.2e9 * infra.wave(c.ts, 300, 0.2, name + role)) * (1 if bdb == "1" else 0.6)
        m = g(redis_up=1, redis_used_memory=used, redis_maxmemory=2e9, redis_used_memory_rss=used * 1.12, redis_mem_fragmentation_ratio=1.1 + 0.05 * r.random(), redis_instantaneous_ops_per_sec=ops,
              redis_process_cpu_usage_percent=8 + 55 * load * (1 if role == "master" else 0.4), redis_connected_clients=20 + 90 * load, redis_blocked_clients=r.choice([0, 0, 1]),
              redis_total_error_replies=r.randrange(0, 3), redis_active_defrag_running=float(r.random() < 0.03), redis_aof_rewrite_in_progress=float(r.random() < 0.04),
              redis_rdb_bgsave_in_progress=float(r.random() < 0.05), redis_current_cow_size=r.randrange(0, 50) * 1e5, redis_current_fork_perc=r.uniform(0, 100) * (r.random() < 0.05),
              redis_eventloop_duration_sum=r.uniform(0.01, 0.2), redis_rdb_changes_since_last_save=r.randrange(1, 5000))
        return metric_doc(REE, c.ts, RE_RES(node), sc, {"redis": f"redis:{bdb}{i % 2 + 1}", "bdb": bdb, "node": str(i % 3 + 1), "role": role}, m)
    i -= 4
    if i < 3:  # proxies
        node = RE_NODES[i]
        m = g(dmcproxy_process_cpu_usage_percent=6 + 40 * load, dmcproxy_process_open_fds=300 + 400 * load, dmcproxy_process_max_fds=65536, dmcproxy_process_resident_memory_bytes=3.2e8 + 4e7 * load,
              dmcproxy_process_virtual_memory_bytes=1.6e9)
        return metric_doc(REE, c.ts, RE_RES(node), sc, {"node": str(i + 1), "proxy": str(i + 1)}, m)
    i -= 3
    bdb, name, _ = RE_DBS[i]  # listeners: one per database, on a rotating node
    node = RE_NODES[(i + c.ts.minute // 10) % 3]
    m = g(listener_acc_latency=0.0006 + 0.0003 * load, listener_acc_read_latency=0.0005, listener_acc_write_latency=0.0007, listener_total_req=infra.counter(c.ts, 900 * (1 if bdb == "1" else 0.5), "lst" + bdb + node, False),
          listener_read_req=infra.counter(c.ts, 650, "lr" + bdb + node, False), listener_write_req=infra.counter(c.ts, 230, "lw" + bdb + node, False), listener_conns=20 + 90 * load,
          listener_auth_errors=float(r.random() < 0.03), listener_max_connections_exceeded=float(r.random() < 0.01))
    return metric_doc(REE, c.ts, RE_RES(node), sc, {"bdb": bdb, "endpoint": f"{bdb}:1", "node": node[-1], "port": str(12000 + int(bdb))}, m)


RE_DOCS = 2 + 3 + 4 + 3 + 2


# =============================== MYSQL (mysqlreceiver: metrics + db query logs) ===============================================
MYM = stream("mysql_otel", "0.6.1", "mysqlreceiver.otel", "metrics")
MYL = stream("mysql_otel", "0.6.1", "mysqlreceiver.otel", "logs")
MY_NODES = MYSQL_NODES[:2]
MY_TABLES = [("shop", "orders"), ("shop", "order_items"), ("billing", "invoices")]
MY_PRIMARY_PLAN = (
    ("base", None), ("threads", "connected"), ("bp_pages", "data"), ("bp_ops", "read_requests"), ("bp_ops", "reads"),
    ("net", "received"), ("net", "sent"), ("handlers", "commit"), ("locks", "immediate"), ("row_ops", "read"),
    ("page_ops", "written"), ("conn_err", "max_connections"), ("bp_data_pages", "dirty"), ("bp_usage", "data"), ("row_locks", "waits"),
    ("tbl_wait", 0), ("tbl_size", 0), ("tbl_size", 2), ("double_writes", "writes"), ("log_ops", "fsyncs"))
MY_REPLICA_PLAN = (("base", None), ("threads", "connected"), ("bp_pages", "data"))


def _mysql(c: Ctx) -> dict:
    i = c.i
    r = c.rng
    if i < len(MY_PRIMARY_PLAN):
        node, role = MY_NODES[0]
        what, arg = MY_PRIMARY_PLAN[i]
    else:
        node, role = MY_NODES[1]
        what, arg = MY_REPLICA_PLAN[i - len(MY_PRIMARY_PLAN)]
    res = host_res(node, "mysql", {"mysql.instance.endpoint": f"{node}:3306"})
    sc = scope("mysqlreceiver", "0.152.0")
    mult = 1.0 if role == "primary" else 0.55
    qps = infra.LoadRate(40 * mult, 520 * mult, c.load)
    cn = lambda rate, key: infra.counter(c.ts, rate, node + key, False)  # noqa: E731
    M = lambda attrs, **m: metric_doc(MYM, c.ts, res, sc, attrs, {k.replace("__", "."): v for k, v in m.items()})  # noqa: E731
    if what == "base":
        m = {"mysql.uptime": int(c.ts.timestamp()) - 1_759_000_000, "mysql.connection.count": cn(0.6 * mult, "cc"), "mysql.max_used_connections": int(60 + 90 * min(c.load, 1.5) / 1.5),
             "mysql.query.count": cn(qps, "qc"), "mysql.query.client.count": cn(qps * 0.97, "qcc"), "mysql.query.slow.count": cn(0.02 * mult, "qsc"), "mysql.buffer_pool.page_flushes": cn(4 * mult, "pf"),
             "mysql.buffer_pool.limit": 8 << 30}
        if role == "replica":
            m["mysql.replica.time_behind_source"] = 0 if r.random() > 0.15 else r.randint(1, 6)
            m["mysql.replica.sql_delay"] = 0
        return metric_doc(MYM, c.ts, res, sc, None, m)
    if what == "threads":
        v = {"connected": int(30 + 100 * min(c.load, 1.5) / 1.5 * mult), "running": r.randint(1, 4 + int(6 * c.load)), "cached": 8, "created": cn(0.01, "tcr")}[arg]
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.threads": v})
    if what == "bp_pages":
        tot = 65536
        data = int(tot * (0.78 + 0.1 * infra.wave(c.ts, 720, 0.1, node)))
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.buffer_pool.pages": {"data": data, "free": tot - data, "misc": 0}[arg]})
    if what == "bp_data_pages":
        return metric_doc(MYM, c.ts, res, sc, {"status": arg}, {"mysql.buffer_pool.data_pages": r.randint(10, 200)})
    if what == "bp_usage":
        return metric_doc(MYM, c.ts, res, sc, {"status": arg}, {"mysql.buffer_pool.usage": int(65536 * 0.8 * 16384)})
    if what == "bp_ops":
        return metric_doc(MYM, c.ts, res, sc, {"operation": arg}, {"mysql.buffer_pool.operations": cn(qps * 6 if arg == "read_requests" else qps * 0.7, "bo" + arg)})
    if what == "net":
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.client.network.io": cn(qps * (180 if arg == "received" else 1400), "ni" + arg)})
    if what == "handlers":
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.handlers": cn(qps * (9 if "rnd" in arg else 0.3), "h" + arg)})
    if what == "locks":
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.locks": cn(qps * 0.5, "lk" + arg)})
    if what == "row_ops":
        return metric_doc(MYM, c.ts, res, sc, {"operation": arg}, {"mysql.row_operations": cn(qps * (4 if arg == "read" else 0.3), "ro" + arg)})
    if what == "page_ops":
        return metric_doc(MYM, c.ts, res, sc, {"operation": arg}, {"mysql.page_operations": cn(qps * 0.1, "po" + arg)})
    if what == "conn_err":
        return metric_doc(MYM, c.ts, res, sc, {"error": arg}, {"mysql.connection.errors": cn(0.001, "ce" + arg) + 3})
    if what == "row_locks":
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.row_locks": cn(qps * 0.02, "rl")})
    if what == "double_writes":
        return metric_doc(MYM, c.ts, res, sc, {"kind": arg}, {"mysql.double_writes": cn(2 * mult, "dw")})
    if what == "log_ops":
        return metric_doc(MYM, c.ts, res, sc, {"operation": arg}, {"mysql.log_operations": cn(5 * mult, "lo")})
    schema, table = MY_TABLES[arg]
    if what == "tbl_wait":
        op = ["fetch", "insert"][arg]
        return metric_doc(MYM, c.ts, res, sc, {"schema": schema, "table": table, "operation": op}, {"mysql.table.io.wait.count": cn(30, "tw" + table + op), "mysql.table.io.wait.time": cn(3.0e7, "twt" + table + op)})
    if what == "tbl_idx":
        return metric_doc(MYM, c.ts, res, sc, {"schema": schema, "table": table, "index": "PRIMARY", "operation": "fetch"}, {"mysql.index.io.wait.count": cn(20, "ix" + table), "mysql.index.io.wait.time": cn(2.0e7, "ixt" + table)})
    # tbl_size: data row with rows + size
    size = int((4e8 if table == "orders" else 1.5e8) * (1 + (c.ts.timestamp() % 86400) / 86400 * 0.01))
    rows = int(size / 190)
    return metric_doc(MYM, c.ts, res, sc, {"schema": schema, "table": table, "kind": "data"}, {"mysql.table.size": size, "mysql.table.rows": rows})


def _mysql_logs(c: Ctx) -> dict:
    """db.server.top_query (digest summaries) and db.server.query_sample (live sessions) log records."""
    r = c.rng
    node, role = MY_NODES[0]
    res = host_res(node, "mysql", {"mysql.instance.endpoint": f"{node}:3306"})
    sc = scope("mysqlreceiver", "0.152.0")
    from . import infra_mysql as my
    text, schema = my.DIGESTS[r.randrange(len(my.DIGESTS))]
    digest = hashlib.sha256(text.encode()).hexdigest()
    if r.random() < 0.6:
        calls = r.randrange(5, 4000)
        attrs = {"db.query.text": text, "db.system.name": "mysql", "mysql.events_statements_summary_by_digest.count_star": calls, "mysql.events_statements_summary_by_digest.digest": digest,
                 "mysql.events_statements_summary_by_digest.sum_timer_wait": round(calls * r.lognormvariate(-6.0, 0.6), 4), "mysql.query_plan": "", "mysql.query_plan.hash": ""}
        return log_doc(MYL, c.ts, res, sc, attrs, None, "INFO", "db.server.top_query")
    attrs = {"db.query.text": text, "db.system.name": "mysql", "db.namespace": schema, "user.name": r.choice(["app_shop", "billing_svc", "reporting"]), "mysql.threads.thread_id": r.randrange(10, 400),
             "mysql.threads.processlist_command": r.choice(["Query", "Sleep", "Execute"]), "mysql.threads.processlist_state": r.choice(["executing", "statistics", "Sending data", "freeing items"]),
             "mysql.wait_type": r.choice(["wait/io/table/sql/handler", "wait/lock/table/sql/handler", "wait/io/socket/sql/client_connection", "wait/synch/mutex/innodb/log_sys_mutex"]),
             "mysql.events_waits_current.timer_wait": round(r.lognormvariate(-6.5, 0.8), 6), "mysql.events_statements_current.timer_wait": round(r.lognormvariate(-5.5, 0.8), 6),
             "mysql.events_statements_current.digest": digest, "mysql.session.status": "waiting", "client.address": "10.20.5.%d" % r.randrange(10, 60)}
    return log_doc(MYL, c.ts, res, sc, attrs, None, "INFO", "db.server.query_sample")


# =============================== KAFKA (kafkametricsreceiver) =================================================================
KAM = stream("kafka_otel", "0.3.1", "kafkametricsreceiver.otel", "metrics")
KAFKA_SUBS = [(g, t) for g, ts in KAFKA_GROUPS for t in ts] + [("dlq-replayer", "dead-letter")]  # the last one is an idle group: no members, growing lag
KRES = {"service.name": "kafka-cluster", "service.instance.id": "kafka-cluster:9092", "host.name": "kafka-collector-1", "os.type": "linux", "kafka.cluster.name": "prod-sin"}


def _kafka(c: Ctx) -> dict:
    i = c.i
    r = c.rng
    sc = scope("kafkametricsreceiver", "9.4.2")
    from . import infra_kafka as kk
    npart = len(KAFKA_TOPICS)
    if i == 0:
        return metric_doc(KAM, c.ts, KRES, sc, None, {"kafka.brokers": len(KAFKA_BROKERS)})
    i -= 1
    # rotate: even 10 minute rounds report topic/partition docs, odd rounds the consumer group docs
    if i < npart:
        t = KAFKA_TOPICS[i]
        cur = infra.counter(c.ts, kk.TOPIC_W[t] * 0.25, f"off{t}0", False)
        return metric_doc(KAM, c.ts, KRES, sc, {"topic": t, "partition": 0}, {"kafka.partition.current_offset": cur, "kafka.partition.oldest_offset": max(0, cur - 6_000_000),
                                                                                  "kafka.partition.replicas": 3, "kafka.partition.replicas_in_sync": 2 if t == "metrics-raw" else 3, "kafka.topic.partitions": 1})  # metrics-raw: a follower is permanently behind
    i -= npart
    g, t = KAFKA_SUBS[i % len(KAFKA_SUBS)]
    cur = infra.counter(c.ts, kk.TOPIC_W[t] * 0.25, f"off{t}0", False)
    lag = int(r.uniform(0, 30)) if g != "analytics-ingest" else int(max(1, r.gauss(900 * c.load + 40, 300)))
    if g == "dlq-replayer":
        lag = int(infra.counter(c.ts, 0.0004, "dlq-otel", False)) % 100000 + 1
    members = 0 if g == "dlq-replayer" else (3 if g == "analytics-ingest" else 2)
    return metric_doc(KAM, c.ts, KRES, sc, {"group": g, "topic": t, "partition": 0}, {"kafka.consumer_group.lag": lag, "kafka.consumer_group.offset": cur - lag, "kafka.consumer_group.lag_sum": lag,
                                                                                        "kafka.consumer_group.offset_sum": cur - lag, "kafka.consumer_group.members": members})


def _kafka_dispatch(c: Ctx) -> dict:
    """Entity index c.i walks brokers (1) + partitions (12) + subscriptions (11) = 24 slots; each 10 minute round reports half of them."""
    half = (c.ts.minute // 10) % 2
    slots = 1 + len(KAFKA_TOPICS) + len(KAFKA_SUBS)
    idx = (c.i * 2 + half) % slots
    return _kafka(Ctx(c.stream, c.ts, idx, c.rng, c.load))


registry.register(
    GROUP,
    Generator(NGX_M, _ngx_metrics, mode="entities", entities=len(OT_NGINX_HOSTS) * 5, every_min=10),
    Generator(NGX_A, _ngx_access, rate_per_min=1.2),
    Generator(NGX_E, _ngx_error, rate_per_min=0.2),
    Generator(ING_A, _ing_access, rate_per_min=1.2),
    Generator(ING_E, _ing_error, rate_per_min=0.2),
    Generator(RED, _redis, mode="entities", entities=10, every_min=10),
    Generator(REE, _ree, mode="entities", entities=RE_DOCS, every_min=10),
    Generator(MYM, _mysql, mode="entities", entities=len(MY_PRIMARY_PLAN) + len(MY_REPLICA_PLAN), every_min=10),
    Generator(MYL, _mysql_logs, rate_per_min=0.8),
    Generator(KAM, _kafka_dispatch, mode="entities", entities=(1 + len(KAFKA_TOPICS) + len(KAFKA_SUBS) + 1) // 2, every_min=10),
)
