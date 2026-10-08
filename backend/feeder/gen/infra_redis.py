"""REDIS (info, key, keyspace metrics; log and slowlog) and Redis Enterprise (node, proxy metrics).

Topology: redis-cache-01 (master) and redis-cache-02 (replica of 01), db0 sessions/cart and db1 cache; a 3 node Redis
Enterprise cluster (rec-sin-1..3) with 2 databases (orders-cache, session-store).
"""
from __future__ import annotations

from datetime import datetime

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra
from .infra import GROUP, REDIS_NODES, S

MAXMEM = 1 << 30
COMMANDS = {"get": 0.45, "set": 0.2, "hget": 0.08, "hset": 0.06, "expire": 0.05, "del": 0.04, "lpush": 0.03, "zadd": 0.03, "incr": 0.03, "mget": 0.03}
KEYS = [("session:alice", "hash", 14, 1800), ("cart:9921", "hash", 6, 900), ("cache:homepage", "string", 1, 300), ("leaderboard:daily", "zset", 4200, -1),
        ("queue:emails", "list", 35, -1), ("feature:flags", "hash", 22, -1)]


def _node(i: int) -> tuple[str, str]:
    return REDIS_NODES[i % len(REDIS_NODES)]


def _info(c: Ctx) -> dict:
    name, role = _node(c.i)
    r = c.rng
    d = infra.metric_base("redis/info", name, module="redis")
    d["service"] = {"address": f"{name}:6379", "type": "redis", "version": "7.4.1"}
    d["process"] = {"pid": 1}
    mult = 1.0 if role == "master" else 0.45  # the replica serves fewer reads
    ops_c = infra.LoadRate(250 * mult, 2400 * mult, c.load)
    ops = max(1, int(float(ops_c) * r.uniform(0.9, 1.1)))
    t = c.ts.timestamp()
    start = 1_759_000_000 + infra.stable(name) % 1000
    used = int((380e6 + 140e6 * infra.wave(c.ts, 240, 0.25, name)) * (1.0 if role == "master" else 0.95))
    peak = int(max(used * 1.12, 520e6))
    ri = d["redis"]["info"]
    ri["clients"].update({"connected": int(40 + 220 * min(c.load, 1.5) / 1.5 * mult + r.randint(0, 6)), "blocked": r.choice([0, 0, 0, 1]), "max_input_buffer": 0, "max_output_buffer": 0})
    ri["cpu"]["used"] = {"sys": round(infra.counter(c.ts, 0.04 * mult, name + "sys", False) / 1000, 3), "user": round(infra.counter(c.ts, 0.09 * mult, name + "usr", False) / 1000, 3),
                         "sys_children": 1.2, "user_children": 4.8}
    ri["memory"].update({"max": {"policy": "allkeys-lru", "value": MAXMEM}, "fragmentation": {"bytes": int(used * 0.08), "ratio": round(1.05 + 0.06 * r.random(), 2)}})
    ri["memory"]["used"] = {"dataset": int(used * 0.82), "lua": 37888, "peak": peak, "rss": int(used * 1.1), "value": used}
    ri["memory"]["allocator_stats"]["allocated"] = used
    ri["memory"]["allocator_stats"]["fragmentation"] = {"bytes": int(used * 0.08), "ratio": 1.07}
    ri["memory"]["allocator_stats"]["rss"] = {"bytes": int(used * 0.04), "ratio": 1.04}
    ri["persistence"]["rdb"]["last_save"] = {"changes_since": r.randrange(0, 4000), "time": int(t) - r.randrange(30, 900)}
    ri["persistence"]["rdb"]["bgsave"].update({"in_progress": False, "current_time": {"sec": -1}, "last_time": {"sec": r.randrange(1, 4)}})
    ri["persistence"]["aof"]["enabled"] = True
    ri["replication"].update({"role": role, "connected_slaves": 1 if role == "master" else 0})
    off = infra.counter(c.ts, 1500 * mult, "repl" + REDIS_NODES[0][0], False)
    ri["replication"]["master"] = {"offset": off if role == "master" else off - r.randrange(0, 900), "second_offset": -1}
    ri["replication"]["backlog"] = {"active": 1, "first_byte_offset": max(0, off - 1048576), "histlen": 1048576, "size": 1048576}
    ri["server"].update({"mode": "standalone", "uptime": int(t) - start, "run_id": f"{infra.stable(name):08x}" * 5, "tcp_port": 6379, "version": "7.4.1", "arch_bits": "64"})
    processed = infra.counter(c.ts, ops_c * 0.6, name + "cmd", False)
    hits = int(processed * 0.46 * 0.88)
    ri["stats"].update({"commands_processed": processed, "connections": {"received": infra.counter(c.ts, 0.4 * mult, name + "conn", False), "rejected": 0},
                        "instantaneous": {"input_kbps": round(ops * 0.05, 2), "ops_per_sec": ops, "output_kbps": round(ops * 0.2, 2)},
                        "keys": {"evicted": infra.counter(c.ts, 0.02, name + "ev", False) if role == "master" else 0, "expired": infra.counter(c.ts, 2.5 * mult, name + "ex", False)},
                        "keyspace": {"hits": hits, "misses": int(hits * 0.136)}, "latest_fork_usec": 800 + r.randrange(0, 400),
                        "net": {"input": {"bytes": infra.counter(c.ts, ops_c * 55, name + "ni", False)}, "output": {"bytes": infra.counter(c.ts, ops_c * 210, name + "no", False)}}})
    ri["slowlog"] = {"count": int(infra.counter(c.ts, 0.001, name + "sl", False))}
    ri["commandstats"] = {cmd: {"calls": int(processed * w), "failed_calls": 0, "rejected_calls": 0, "usec": int(processed * w * 3.2), "usec_per_call": round(1.5 + 8 * w, 2)}
                          for cmd, w in COMMANDS.items()}
    return d


def _keyspace(c: Ctx) -> dict:
    name, role = _node(c.i // 2)
    db = c.i % 2
    r = c.rng
    d = infra.metric_base("redis/keyspace", name, module="redis")
    d["service"] = {"address": f"{name}:6379", "type": "redis"}
    keys = int((42000 if db == 0 else 9000) * infra.wave(c.ts, 360, 0.08, name + str(db)) * (1 if role == "master" else 0.98))
    d["redis"] = {"keyspace": {"avg_ttl": int(r.uniform(2.5e5, 9e5)), "expires": int(keys * (0.7 if db == 0 else 0.95)), "id": f"db{db}", "keys": keys}}
    return d


def _key(c: Ctx) -> dict:
    name, role = _node(c.i // 3)
    kname, ktype, length, ttl = KEYS[(c.i % 3) + 3 * (c.ts.minute // 10 % 2)]
    r = c.rng
    db = 1 if kname.startswith("cache:") else 0
    d = infra.metric_base("redis/key", name, module="redis")
    d["service"] = {"address": f"{name}:6379", "type": "redis"}
    d["redis"] = {"key": {"expire": {"ttl": ttl if ttl < 0 else max(1, ttl - r.randrange(0, 200))}, "id": f"{db}:{kname}", "length": length + r.randrange(0, 3), "name": kname, "type": ktype},
                  "keyspace": {"id": f"db{db}"}}
    return d


MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LOGS = [("*", "Background saving started by pid {pid}", 0.12), ("*", "DB saved on disk", 0.12), ("*", "Background saving terminated with success", 0.1),
        ("*", "{n} changes in 300 seconds. Saving...", 0.1), ("*", "Synchronization with replica redis-cache-02:6379 succeeded", 0.05),
        ("#", "WARNING: /proc/sys/net/core/somaxconn is set to the lower value of 128.", 0.04), ("*", "Partial resynchronization request from redis-cache-02:6379 accepted", 0.05),
        ("-", "Accepted 10.20.7.{ip}:51234", 0.05), ("-", "DB 0: {k} keys ({e} volatile) in 65536 slots HT.", 0.2), ("-", "{cl} clients connected (1 replicas), {mem} bytes in use", 0.17)]


def _log(c: Ctx) -> dict:
    r = c.rng
    name, role = _node(r.randrange(2))
    lv, text, _ = r.choices(LOGS, weights=[x[2] for x in LOGS])[0]
    text = text.format(pid=r.randrange(2000, 30000), n=r.randrange(1, 900), ip=r.randrange(2, 90), k=r.randrange(30000, 50000), e=r.randrange(20000, 40000), cl=r.randrange(40, 280),
                       mem=r.randrange(300_000_000, 500_000_000))
    ts = c.ts
    pid = 1
    line = f"{pid}:{'M' if role == 'master' else 'S'} {ts.day:02d} {MON[ts.month - 1]} {ts.year} {ts:%H:%M:%S}.{ts.microsecond // 1000:03d} {lv} {text}"
    d = infra.log_base(name, "/var/log/redis/redis-server.log")
    d["message"] = line
    d["service"] = {"type": "redis", "version": "7.4.1"}
    d["event"] = {"timezone": "+00:00"}
    return d


SLOW = [("GET", "session:*", 0.2), ("HGETALL", "cart:*", 0.25), ("ZRANGE", "leaderboard:daily", 0.2), ("KEYS", "session:*", 0.1), ("SORT", "queue:emails", 0.1), ("LRANGE", "queue:emails", 0.15)]


def _slowlog(c: Ctx) -> dict:
    r = c.rng
    name, _ = REDIS_NODES[0]  # slow commands are recorded on the master
    cmd, key, _w = r.choices(SLOW, weights=[x[2] for x in SLOW])[0]
    dur = int(r.lognormvariate(9.3, 0.7))  # microseconds, 10 ms median
    if cmd == "KEYS":
        dur *= 6
    d = infra.log_base(name, "/var/log/redis/slowlog")
    d["redis"] = {"slowlog": {"cmd": cmd, "key": key, "args": [cmd.lower(), key, "0", "-1"] if cmd in ("ZRANGE", "LRANGE") else [cmd.lower(), key], "duration": {"us": dur},
                              "id": infra.counter(c.ts, 0.005, "slowid", False)}}
    d["service"] = {"type": "redis", "version": "7.4.1"}
    d["event"] = {"duration": dur * 1000}
    d["message"] = f"{cmd.lower()} {key}"
    return d


# ---- Redis Enterprise (Prometheus style metrics scraped from the cluster) ------------------------------------------------------
RE_NODES = ["rec-sin-1", "rec-sin-2", "rec-sin-3"]
RE_DBS = [("1", "orders-cache"), ("2", "session-store")]


def _re_node(c: Ctx) -> dict:
    node = RE_NODES[c.i % 3]
    r = c.rng
    d = infra.metric_base("redisenterprise/node", node, module="prometheus")
    lab = d["redisenterprise"]["node"]["labels"]
    lab.update({"cluster": "rec.corp.example.org", "node": str(c.i % 3 + 1), "instance": f"{node}:8070", "addr": f"10.20.8.{c.i % 3 + 11}", "job": "redis-enterprise"})
    d["service"] = {"address": f"{node}:8070", "type": "prometheus"}
    d["host"]["name"] = node
    n = d["redisenterprise"]["node"]
    for k in list(n):
        if k == "labels":
            continue
        n[k] = n[k] if not isinstance(n[k], dict) else n[k]
    n.update({"up": {"value": 1}, "conns": {"value": int(30 + 140 * c.load / 1.5 + r.randrange(0, 5))}, "cpu_idle": {"value": round(0.9 - 0.4 * c.load / 1.5, 3)},
              "cpu_system": {"value": round(0.04 + 0.05 * c.load / 1.5, 3)}, "cpu_user": {"value": round(0.1 + 0.2 * c.load / 1.5, 3)},
              "egress_bytes": {"value": int(infra.counter(c.ts, 2e5, node + "eg", False))}, "ingress_bytes": {"value": int(infra.counter(c.ts, 6e4, node + "ig", False))},
              "free_memory": {"value": int(9e9 - 1.5e9 * c.load / 1.5 + r.gauss(0, 5e7))}, "available_memory": {"value": int(9.5e9 - 1.2e9 * c.load / 1.5)},
              "ephemeral_storage_free": {"value": int(60e9 - infra.counter(c.ts, 20, node + "es", False) % 1e9)}, "ephemeral_storage_avail": {"value": int(55e9)},
              "persistent_storage_free": {"value": int(200e9)}, "persistent_storage_avail": {"value": int(190e9)}})
    return d


def _re_proxy(c: Ctx) -> dict:
    node = RE_NODES[c.i % 3]
    dbid, dbn = RE_DBS[c.i // 3 % len(RE_DBS)]
    r = c.rng
    d = infra.metric_base("redisenterprise/proxy", node, module="prometheus")
    d["host"]["name"] = node
    lab = d["redisenterprise"]["proxy"]["labels"]
    lab.update({"bdb": dbid, "cluster": "rec.corp.example.org", "proxy": str(c.i % 3 + 1), "node": str(c.i % 3 + 1), "endpoint": f"{dbid}:1", "instance": f"{node}:8070", "port": str(12000 + int(dbid)),
                "job": "redis-enterprise"})
    return infra.fill(d, "redisenterprise/proxy", c, base=1.0 + 0.3 * (c.i % 3), zeros=True)


registry.register(
    GROUP,
    Generator(S["redis/info"], _info, mode="entities", entities=2, every_min=5),
    Generator(S["redis/keyspace"], _keyspace, mode="entities", entities=4, every_min=10),
    Generator(S["redis/key"], _key, mode="entities", entities=2 * 3, every_min=10),
    Generator(S["redis/log"], _log, rate_per_min=0.7),
    Generator(S["redis/slowlog"], _slowlog, rate_per_min=0.4),
    Generator(S["redisenterprise/node"], _re_node, mode="entities", entities=3, every_min=5),
    Generator(S["redisenterprise/proxy"], _re_proxy, mode="entities", entities=6, every_min=10),
)
