"""PostgreSQL: server log lines (package `postgresql`, RAW through the package pipeline) and OpenTelemetry shaped metrics and
logs of the `postgresqlreceiver` (package `postgresql_otel`, written to `*-postgresqlreceiver.otel-synthetic`).

Estate: pg-orders-01 (databases orders_db and inventory_db) and pg-analytics-01 (analytics_db).
The real receiver data of other demos lives in the `default` and `trading-*` namespaces of the same data streams; the synthetic
series use their own namespace and instance ids, with the same counter / gauge mappings the real data has.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra, rest
from .infra_otel import host_res, log_doc, metric_doc, scope, stream

LOG = rest.S["postgresql/log"]
PGM = stream("postgresql_otel", "0.5.0", "postgresqlreceiver.otel", "metrics")
PGL = stream("postgresql_otel", "0.5.0", "postgresqlreceiver.otel", "logs")
INSTANCES = [("pg-orders-01:5432", ["orders_db", "inventory_db"], 1.0), ("pg-analytics-01:5432", ["analytics_db"], 0.35)]
USERS = ["app_user", "reporting", "billing_svc", "etl_loader"]
QUERIES = [
    ("SELECT o.id, o.total FROM orders o WHERE o.customer_id = $1 ORDER BY o.created_at DESC LIMIT 20", "orders_db", 0.4),
    ("INSERT INTO orders (customer_id, total, status) VALUES ($1, $2, 'new')", "orders_db", 0.9),
    ("UPDATE inventory SET stock = stock - $1 WHERE sku = $2", "inventory_db", 1.1),
    ("SELECT sku, stock FROM inventory WHERE warehouse_id = $1 AND stock < $2", "inventory_db", 6.0),
    ("SELECT date_trunc('day', created_at) d, count(*), sum(total) FROM orders GROUP BY 1 ORDER BY 1", "analytics_db", 420.0),
    ("SELECT c.region, avg(o.total) FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.region", "analytics_db", 910.0),
    ("DELETE FROM sessions WHERE expires_at < now()", "orders_db", 38.0),
    ("SELECT * FROM events e JOIN users u ON u.id = e.user_id WHERE e.created_at > now() - interval '1 day'", "analytics_db", 1800.0),
    ("COPY staging_events FROM STDIN", "analytics_db", 260.0),
    ("SELECT count(*) FROM order_items WHERE order_id = ANY($1)", "orders_db", 3.5)]


# ----------------------------------------------- server log (raw line) ---------------------------------------------------
def _log(c: Ctx) -> dict:
    r = c.rng
    pid = r.randrange(300, 9000)
    ts = f"{c.ts:%Y-%m-%d %H:%M:%S}.{c.ts.microsecond // 1000:03d} UTC"
    q, db, base = r.choices(QUERIES, weights=[10, 8, 8, 4, 2, 1, 2, 1, 1, 4])[0]
    user = USERS[r.randrange(len(USERS))] if db != "analytics_db" else r.choice(["reporting", "etl_loader"])
    k = r.random()
    if k < 0.55:
        ms = base * r.lognormvariate(0, 0.9) * (0.8 + 0.4 * min(c.load, 1.5) / 1.5)
        line = f"{ts} [{pid}] {user}@{db} LOG:  duration: {ms:.3f} ms  " + (r.choice(["statement: ", "execute <unnamed>: "]) + q)
    elif k < 0.70:
        line = r.choice([f"{ts} [{pid}] {user}@{db} ERROR:  duplicate key value violates unique constraint \"orders_pkey\"",
                         f"{ts} [{pid}] {user}@{db} ERROR:  deadlock detected",
                         f"{ts} [{pid}] {user}@{db} ERROR:  canceling statement due to statement timeout",
                         f"{ts} [{pid}] {user}@{db} ERROR:  relation \"order_archive\" does not exist at character 15"])
    elif k < 0.82:
        line = r.choice([f"{ts} [{pid}] {user}@{db} WARNING:  there is no transaction in progress",
                         f"{ts} [{pid}] {user}@{db} WARNING:  nonstandard use of escape in a string literal"])
    elif k < 0.88:
        line = f"{ts} [{pid}] [unknown]@[unknown] FATAL:  password authentication failed for user \"{r.choice(USERS)}\""
    elif k < 0.94:
        line = f"{ts} [88] LOG:  checkpoint starting: {r.choice(['time', 'wal', 'immediate force wait'])}"
    else:
        line = f"{ts} [88] LOG:  checkpoint complete: wrote {r.randrange(50, 4000)} buffers ({r.uniform(0.3, 12):.1f}%); 0 WAL file(s) added, 0 removed, {r.randrange(0, 3)} recycled"
    h = f"pg-{'orders' if db != 'analytics_db' else 'analytics'}-01"
    d = infra.log_base(h, "/var/lib/postgresql/data/log/postgresql.log")
    d["message"] = line
    d["tags"] = ["postgresql-log"]
    return d


# ----------------------------------------------- OTel metrics ---------------------------------------------------------------
KINDS = {"postgresql.backends": "gl", "postgresql.database.locks": "gl", "postgresql.db_size": "gl", "postgresql.connection.max": "gl", "postgresql.database.count": "gl",
         "postgresql.bgwriter.duration": "cd"}
for n in ("commits", "rollbacks", "blks_hit", "blks_read", "deadlocks", "temp_files", "temp.io", "tup_inserted", "tup_updated", "tup_deleted", "tup_fetched",
          "tup_returned", "bgwriter.maxwritten", "bgwriter.buffers.allocated", "bgwriter.buffers.writes", "bgwriter.checkpoint.count"):
    KINDS["postgresql." + n] = "cl"
LOCKS = [("relation", "AccessShareLock", "orders"), ("relation", "RowExclusiveLock", "orders"), ("relation", "RowExclusiveLock", "inventory"),
         ("transactionid", "ExclusiveLock", ""), ("relation", "AccessShareLock", "order_items"), ("tuple", "ExclusiveLock", "inventory")]
PLAN: list[tuple] = []
for _inst, _dbs, _m in INSTANCES:
    PLAN.append(("inst", _inst, None, 0))
    for _db in _dbs:
        PLAN.append(("db", _inst, _db, 0))
        for _k in range(len(LOCKS) if _m == 1.0 else 3):
            PLAN.append(("lock", _inst, _db, _k))


def _res(inst: str, db: str | None) -> dict:
    r = {"service.instance.id": inst}
    if db:
        r["postgresql.database.name"] = db
    return r


def _pg_metrics(c: Ctx) -> dict:
    what, inst, db, k = PLAN[c.i % len(PLAN)]
    mult = next(m for i, _d, m in INSTANCES if i == inst)
    r = c.rng
    sc = scope("postgresqlreceiver", "0.152.0")
    cn = lambda rate, key: infra.counter(c.ts, rate, inst + str(db) + key, False)  # noqa: E731
    rare = lambda rate, key: int((c.ts.timestamp() - infra.ANCHOR) * rate * 0.55) + infra.stable(inst, db, key) % 20  # noqa: E731  (small monotonic totals)
    if what == "inst":
        m = {"postgresql.connection.max": 100, "postgresql.database.count": len(next(d for i, d, _ in INSTANCES if i == inst)),
             "postgresql.bgwriter.maxwritten": rare(0.0004 * mult, "mw"), "postgresql.bgwriter.buffers.allocated": cn(30 * mult, "ba"),
             "postgresql.bgwriter.buffers.writes": cn(22 * mult, "bw"), "postgresql.bgwriter.checkpoint.count": rare(0.003, "ck"),
             "postgresql.bgwriter.duration": float(cn(40 * mult, "bd"))}
        return metric_doc(PGM, c.ts, _res(inst, None), sc, None, m, KINDS)
    if what == "db":
        tps = infra.LoadRate(30 * mult, 260 * mult, c.load)
        hit = cn(tps.scaled(55), "bh")
        m = {"postgresql.backends": int(6 + 34 * min(c.load, 1.5) / 1.5 * mult + r.randint(0, 3)), "postgresql.commits": cn(tps, "cm"),
             "postgresql.rollbacks": cn(tps.scaled(0.015), "rb"), "postgresql.blks_hit": hit, "postgresql.blks_read": cn(tps.scaled(0.9), "br"),
             "postgresql.deadlocks": rare(0.0002 * mult, "dl"), "postgresql.temp_files": rare(0.012 * mult, "tf"), "postgresql.temp.io": rare(0.012 * mult * 9e6, "ti"),
             "postgresql.tup_inserted": cn(tps.scaled(1.8), "ti1"), "postgresql.tup_updated": cn(tps.scaled(1.1), "tu"), "postgresql.tup_deleted": cn(tps.scaled(0.25), "td"),
             "postgresql.tup_fetched": cn(tps.scaled(14), "tf1"), "postgresql.tup_returned": cn(tps.scaled(60), "tr"),
             "postgresql.db_size": int((4.2e9 if db == "analytics_db" else 6.5e8) * infra.wave(c.ts, 1440 * 30, 0.02, db))}
        return metric_doc(PGM, c.ts, _res(inst, db), sc, None, m, KINDS)
    lt, mode, rel = LOCKS[k % len(LOCKS)]
    n = max(0, int(r.gauss(3 * mult + 5 * min(c.load, 1.5) / 1.5 * mult, 1.5))) + (1 if lt == "relation" else 0)
    attrs = {"lock_type": lt, "mode": mode}
    if rel:
        attrs["relation"] = rel
    return metric_doc(PGM, c.ts, _res(inst, db), sc, attrs, {"postgresql.database.locks": n}, KINDS)


# ----------------------------------------------- OTel logs (query samples and top queries) -----------------------------------
def _pg_logs(c: Ctx) -> dict:
    r = c.rng
    inst, dbs, mult = INSTANCES[0] if r.random() < 0.75 else INSTANCES[1]
    q, db, base = r.choice([x for x in QUERIES if x[1] in dbs])
    res = host_res(inst.split(":")[0], "postgresql", {"service.instance.id": inst})
    sc = scope("postgresqlreceiver", "0.152.0")
    digest = int.from_bytes(hashlib.sha256(q.encode()).digest()[:7], "big")
    if r.random() < 0.55:
        calls = r.randrange(5, 5000)
        attrs = {"db.namespace": db, "db.query.text": q.replace("$1", "?").replace("$2", "?"), "db.system.name": "postgresql", "postgresql.calls": calls,
                 "postgresql.queryid": str(digest), "postgresql.rolname": r.choice(USERS), "postgresql.rows": int(calls * r.uniform(0.5, 30)),
                 "postgresql.shared_blks_hit": calls * r.randrange(2, 40), "postgresql.shared_blks_read": r.randrange(0, 200), "postgresql.temp_blks_read": 0,
                 "postgresql.temp_blks_written": 0, "postgresql.total_exec_time": round(calls * base * r.uniform(0.7, 1.3), 3), "postgresql.total_plan_time": 0.0}
        return log_doc(PGL, c.ts, res, sc, attrs, None, "INFO", "db.server.top_query")
    state = r.choices(["active", "idle in transaction", "idle", "active"], weights=[5, 2, 2, 3])[0]
    wt = r.choice(["Lock", "IO", "Client", "LWLock", "IPC", ""])
    attrs = {"db.namespace": db, "db.query.text": q.replace("$1", "?").replace("$2", "?"), "db.system.name": "postgresql", "postgresql.state": state,
             "postgresql.total_exec_time": round(base * r.lognormvariate(0, 0.8), 3), "postgresql.wait_event_type": wt,
             "postgresql.wait_event": {"Lock": "transactionid", "IO": "DataFileRead", "Client": "ClientRead", "LWLock": "WALWrite", "IPC": "BufferIO", "": ""}[wt],
             "user.name": r.choice(USERS), "network.peer.address": f"10.20.5.{r.randrange(10, 60)}", "postgresql.application_name": r.choice(["orders-api", "billing-worker", "metabase", "psql"]),
             "postgresql.pid": r.randrange(300, 9000)}
    return log_doc(PGL, c.ts, res, sc, attrs, None, "INFO", "db.server.query_sample")


registry.register(rest.GROUP, Generator(LOG, _log, rate_per_min=1.2),
                  Generator(PGM, _pg_metrics, mode="entities", entities=len(PLAN), every_min=10),
                  Generator(PGL, _pg_logs, rate_per_min=1.0))
