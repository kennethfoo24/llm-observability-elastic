"""MYSQL: status, performance, replica_status, galera_status metrics; slowlog and error logs.

Topology: mysql-primary-01 with two replicas (mysql-replica-01, mysql-replica-02) replicating from it, schemas shop and billing;
the Galera panel set is fed by the same three nodes (cluster size 3, state Synced).
"""
from __future__ import annotations

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra
from .infra import GROUP, MYSQL_NODES, S

SCHEMAS = ["shop", "billing"]
TABLES = [("shop", "orders", "PRIMARY"), ("shop", "order_items", "idx_order"), ("shop", "customers", "PRIMARY"), ("billing", "invoices", "idx_customer"), ("billing", "payments", "PRIMARY")]
DIGESTS = [("SELECT * FROM `orders` WHERE `customer_id` = ? ORDER BY `created_at` DESC LIMIT ?", "shop"), ("INSERT INTO `order_items` ( `order_id` , `sku` , `qty` ) VALUES (...)", "shop"),
           ("UPDATE `payments` SET `status` = ? WHERE `id` = ?", "billing"), ("SELECT COUNT ( * ) FROM `invoices` WHERE `due_date` < ?", "billing")]
MYSQL_PORT = 3306


def _n(i: int):
    return MYSQL_NODES[i % len(MYSQL_NODES)]


def _status(c: Ctx) -> dict:
    name, role = _n(c.i)
    r = c.rng
    d = infra.metric_base("mysql/status", name, module="mysql")
    d["service"] = {"address": f"{name}:{MYSQL_PORT}", "type": "mysql"}
    mult = 1.0 if role == "primary" else 0.55
    qps = (40 + 520 * min(c.load, 1.5) / 1.5) * mult * r.uniform(0.9, 1.1)
    q = infra.counter(c.ts, qps, name + "q", False)
    st = d["mysql"]["status"]
    st.update({"queries": q, "questions": int(q * 0.97), "connections": infra.counter(c.ts, 0.6 * mult, name + "conn", False), "max_used_connections": int(60 + 90 * min(c.load, 1.5) / 1.5),
               "opened_tables": 400 + infra.stable(name) % 200, "flush_commands": 12})
    st["aborted"] = {"clients": int(infra.counter(c.ts, 0.0004, name + "ac", False)), "connects": int(infra.counter(c.ts, 0.0003, name + "ae", False))}
    st["bytes"] = {"received": infra.counter(c.ts, qps * 180, name + "br", False), "sent": infra.counter(c.ts, qps * 1400, name + "bs", False)}
    sel = 0.72 if role == "replica" else 0.5
    st["command"] = {"select": infra.counter(c.ts, qps * sel, name + "cs", False), "insert": infra.counter(c.ts, qps * 0.2 * (1 if role == "primary" else 0.02), name + "ci", False),
                     "update": infra.counter(c.ts, qps * 0.15 * (1 if role == "primary" else 0.02), name + "cu", False), "delete": infra.counter(c.ts, qps * 0.02 * (1 if role == "primary" else 0.02), name + "cd", False)}
    st["threads"] = {"cached": int(r.uniform(4, 12)), "connected": int(30 + 100 * min(c.load, 1.5) / 1.5 * mult), "created": infra.counter(c.ts, 0.01, name + "tc", False), "running": r.randint(1, 4 + int(6 * c.load))}
    st["open"] = {"files": 20 + r.randrange(0, 8), "streams": 0, "tables": 330 + r.randrange(0, 10)}
    st["created"] = {"tmp": {"disk_tables": infra.counter(c.ts, 0.03, name + "dt", False), "files": 6, "tables": infra.counter(c.ts, 1.4 * mult, name + "tt", False)}}
    bp = st["innodb"]["buffer_pool"]
    total = 65536
    data = int(total * (0.78 + 0.1 * infra.wave(c.ts, 720, 0.1, name)))
    bp["pages"] = {"data": data, "dirty": r.randint(10, 200), "flushed": infra.counter(c.ts, 4 * mult, name + "fl", False), "free": total - data, "misc": 0, "total": total}
    bp["bytes"] = {"data": data * 16384, "dirty": r.randint(10, 200) * 16384}
    bp["pool"] = {"reads": infra.counter(c.ts, 3 * mult, name + "pr", False), "wait_free": 0}
    bp["read"] = {"ahead": 0, "ahead_evicted": 0, "ahead_rnd": 0, "requests": infra.counter(c.ts, qps * 6, name + "rr", False)}
    bp["write_requests"] = infra.counter(c.ts, qps * 0.8 * (1 if role == "primary" else 0.05), name + "wr", False)
    st["handler"].update({"commit": infra.counter(c.ts, qps * 0.3, name + "hc", False), "external_lock": infra.counter(c.ts, qps * 2, name + "hx", False)})
    st["handler"]["read"].update({"key": infra.counter(c.ts, qps * 3, name + "hk", False), "rnd_next": infra.counter(c.ts, qps * 9, name + "hn", False), "first": infra.counter(c.ts, qps * 0.2, name + "hf", False)})
    st["binlog"] = {"cache": {"disk_use": 0, "use": infra.counter(c.ts, 2 * mult, name + "bc", False)}}
    return d


def _performance(c: Ctx) -> dict:
    name, role = _n(c.i // 4)
    k = c.i % 4
    r = c.rng
    d = infra.metric_base("mysql/performance", name, module="mysql")
    d["service"] = {"address": f"{name}:{MYSQL_PORT}", "type": "mysql"}
    if k < 2:
        text, schema = DIGESTS[(k + (2 if role == "replica" else 0)) % len(DIGESTS)] if role == "replica" else DIGESTS[k]
        avg = int(r.lognormvariate(21.5, 0.5))  # picoseconds, about 2 ms
        d["mysql"]["performance"] = {"events_statements": {"avg": {"timer": {"wait": avg}}, "count": {"star": infra.counter(c.ts, 3.0, name + text, False)}, "digest": {"text": text},
                                                           "last": {"seen": profile.iso(c.ts).replace("Z", "")}, "max": {"timer": {"wait": int(avg * 12)}},
                                                           "quantile": {"95": int(avg * 3.5)}, "query_id": f"{infra.stable(text):08x}", "schemaname": schema}}
    else:
        schema, table, idx = TABLES[(k + c.i // 4) % len(TABLES)]
        d["mysql"]["performance"] = {"table_io_waits": {"count": {"fetch": infra.counter(c.ts, 20.0, name + table, False)}, "index": {"name": idx}, "object": {"name": table, "schema": schema}}}
    return d


def _replica(c: Ctx) -> dict:
    """Raw `sql` metricset output (sql.metrics.*): the package pipeline renames it to mysql.replica_status.* and removes `sql`."""
    name, _ = MYSQL_NODES[1 + c.i % 2]
    r = c.rng
    d = infra.metric_base("mysql/replica_status", name, module="mysql")
    d["service"] = {"address": f"{name}:{MYSQL_PORT}", "type": "mysql"}
    d.pop("mysql", None)
    d.pop("source", None)
    d.pop("user", None)
    pos = infra.counter(c.ts, 2200, "binlogpos", False)
    lag = 0 if r.random() > 0.12 else r.randint(1, 4)
    if c.i % 2 == 1 and r.random() < 0.05:
        lag = r.randint(8, 40)  # replica-02 occasionally falls behind
    binlog = f"mysql-bin.{pos // 5_000_000 + 1:06d}"
    d["sql"] = {"metrics": {
        "string": {"source_host": MYSQL_NODES[0][0], "source_log_file": binlog, "relay_source_log_file": binlog, "source_uuid": "06a246d4-4436-11ef-b5ed-0242c0a8fb02", "source_user": "repl",
                   "replica_io_running": "Yes", "replica_sql_running": "Yes", "replica_io_state": "Waiting for source to send event",
                   "replica_sql_running_state": "Replica has read all relay log; waiting for more updates", "relay_log_file": f"{name}-relay-bin.{pos // 5_000_000 + 1:06d}",
                   "source_info_file": "mysql.slave_master_info", "source_ssl_allowed": "No", "until_condition": "None",
                   "executed_gtid_set": f"06d1322f-4436-11ef-b5bf-0242c0a8fb05:1-{pos // 900}"},
        "numeric": {"seconds_behind_source": lag, "source_server_id": 1, "source_port": MYSQL_PORT, "source_retry_count": 86400, "exec_source_log_pos": pos % 5_000_000 - lag * 900,
                    "read_source_log_pos": pos % 5_000_000, "relay_log_pos": pos % 5_000_000, "relay_log_space": 543 + pos % 9000, "connect_retry": 60, "skip_counter": 0,
                    "sql_delay": 0, "last_errno": 0, "last_io_errno": 0, "last_sql_errno": 0}}}
    return d


def _galera(c: Ctx) -> dict:
    name, _ = _n(c.i)
    r = c.rng
    d = infra.metric_base("mysql/galera_status", name, module="mysql")
    d["service"] = {"address": f"{name}:{MYSQL_PORT}", "type": "mysql"}
    g = d["mysql"]["galera_status"]
    g["cluster"] = {"conf_id": 14, "size": 3, "status": "Primary"}
    g["local"].update({"state": "Synced", "commits": infra.counter(c.ts, 3, name + "gc", False), "recv": {"queue": r.randint(0, 2), "queue_avg": round(r.uniform(0.01, 0.4), 3), "queue_max": 3, "queue_min": 0},
                       "send": {"queue": 0, "queue_avg": round(r.uniform(0, 0.2), 3), "queue_max": 2, "queue_min": 0}, "cert_failures": 0, "bf_aborts": 0, "replays": 0})
    g["last_committed"] = infra.counter(c.ts, 3, "galera", False)
    g["received"] = {"bytes": infra.counter(c.ts, 4000, name + "grb", False), "count": infra.counter(c.ts, 3, name + "grc", False)}
    g["repl"] = {"bytes": infra.counter(c.ts, 3500, name + "gb", False), "count": infra.counter(c.ts, 3, name + "gn", False), "data_bytes": infra.counter(c.ts, 3000, name + "gd", False),
                 "keys": infra.counter(c.ts, 8, name + "gk", False), "keys_bytes": infra.counter(c.ts, 280, name + "gkb", False), "other_bytes": 0}
    g["flow_ctl"] = {"paused": round(r.uniform(0, 0.01), 4), "paused_ns": 0, "recv": 0, "sent": 0}
    g["apply"] = {"oooe": 0, "oool": 0, "window": round(r.uniform(1, 1.6), 2)}
    g["commit"] = {"oooe": 0, "window": round(r.uniform(1, 1.4), 2)}
    g["connected"], g["ready"] = "ON", "ON"
    return d


APPS = [("app_shop", "web-app-01"), ("app_shop", "web-app-02"), ("billing_svc", "billing-01"), ("reporting", "bi-01"), ("root", "localhost")]
SLOWQ = ["SELECT o.*, c.name FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.status = 'pending' ORDER BY o.created_at DESC",
         "SELECT COUNT(*), SUM(total) FROM invoices WHERE due_date < NOW() - INTERVAL 30 DAY", "UPDATE payments SET status = 'settled' WHERE batch_id = 4521",
         "SELECT * FROM order_items WHERE sku LIKE '%case%'", "INSERT INTO audit_log SELECT * FROM audit_staging", "SELECT customer_id, MAX(created_at) FROM orders GROUP BY customer_id"]


def _slowlog(c: Ctx) -> dict:
    r = c.rng
    name, role = MYSQL_NODES[r.choices([0, 1, 2], weights=[5, 3, 2])[0]]
    user, host = APPS[r.randrange(len(APPS))]
    qt = round(r.lognormvariate(0.9, 0.8), 6)
    ts = c.ts
    q = r.choice(SLOWQ)
    lines = [f"# Time: {ts:%Y-%m-%dT%H:%M:%S}.{ts.microsecond:06d}Z", f"# User@Host: {user}[{user}] @ {host} [10.20.5.{r.randrange(10, 60)}]  Id: {r.randrange(100, 9000)}",
             f"# Query_time: {qt:.6f}  Lock_time: {r.uniform(0, 0.001):.6f} Rows_sent: {r.randrange(1, 500)}  Rows_examined: {int(qt * r.randrange(40_000, 400_000))}",
             f"SET timestamp={int(ts.timestamp())};", q + ";"]
    d = infra.log_base(name, "/var/log/mysql/mysql-slow.log")
    d["message"] = "\n".join(lines)
    d["event"] = {"timezone": "+00:00"}
    return d


ERRS = [("Warning", "MY-010055", "Server", "IP address '10.20.5.{n}' could not be resolved: Name or service not known", 0.15), ("Note", "MY-010914", "Server", "Aborted connection {n} to db: 'shop' user: 'app_shop' host: '10.20.5.{n}' (Got timeout reading communication packets).", 0.25),
        ("Warning", "MY-013360", "Server", "Plugin mysql_native_password reported: ''mysql_native_password' is deprecated and will be removed in a future release.'", 0.1),
        ("Note", "MY-010051", "Server", "Replica SQL thread for channel '' initialized, starting replication in log 'mysql-bin.00000{n}' at position 4", 0.05),
        ("Warning", "MY-012637", "InnoDB", "[InnoDB] {n} threads (of 128) are in use, buffer pool resize may be slow", 0.1),
        ("Error", "MY-001205", "Server", "Lock wait timeout exceeded; try restarting transaction (table: shop.orders)", 0.15), ("Note", "MY-011953", "Server", "Event Scheduler: Loaded 0 events", 0.2)]


def _error(c: Ctx) -> dict:
    r = c.rng
    name, role = MYSQL_NODES[r.randrange(len(MYSQL_NODES))]
    lvl, code, sub, text, _ = r.choices(ERRS, weights=[e[4] for e in ERRS])[0]
    text = text.format(n=r.randrange(2, 90))
    ts = c.ts
    d = infra.log_base(name, "/var/log/mysql/error.log")
    d["message"] = f"{ts:%Y-%m-%dT%H:%M:%S}.{ts.microsecond:06d}Z {r.randrange(0, 30)} [{lvl}] [{code}] [{sub}] {text}"
    d["event"] = {"timezone": "+00:00"}
    return d


registry.register(
    GROUP,
    Generator(S["mysql/status"], _status, mode="entities", entities=3, every_min=5),
    Generator(S["mysql/performance"], _performance, mode="entities", entities=12, every_min=10),
    Generator(S["mysql/replica_status"], _replica, mode="entities", entities=2, every_min=5),
    Generator(S["mysql/galera_status"], _galera, mode="entities", entities=3, every_min=10),
    Generator(S["mysql/slowlog"], _slowlog, rate_per_min=0.8),
    Generator(S["mysql/error"], _error, rate_per_min=0.4),
)
