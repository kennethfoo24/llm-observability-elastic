"""KAFKA broker/topic/consumer group metrics and logs, and Kafka Connect.

Topology: 3 brokers (kafka-broker-1..3, ids 1..3, KRaft controllers), 12 topics with 1 partition each (replication factor 3),
5 consumer groups, 2 producers, a 2 worker Kafka Connect cluster with 3 connectors. Metric documents are field-driven from the
package field lists (feeder/templates/kafka/*.fields.json) with explicit values for the dimensions and the key gauges.
"""
from __future__ import annotations

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra
from .infra import GROUP, KAFKA_BROKERS, KAFKA_GROUPS, KAFKA_TOPICS, S

PARTS = 1
BROKER_HOSTS = {b: f"kafka-broker-{b}" for b in KAFKA_BROKERS}
PARTITIONS = [(t, p) for t in KAFKA_TOPICS for p in range(PARTS)]
# topic weight (relative traffic), the heavy hitters first
TOPIC_W = dict(zip(KAFKA_TOPICS, [10, 7, 3, 3, 14, 12, 2, 4, 9, 5, 6, 0.2]))


def leader(topic: str, part: int) -> int:
    return KAFKA_BROKERS[(infra.stable(topic, part) % 3)]


def host_doc(key: str, broker: int, ts=None) -> dict:
    h = BROKER_HOSTS[broker]
    d = infra.metric_base(key, h, module="kafka")
    d["service"] = {"address": f"{h}:9999", "type": "kafka"}
    return d


def _broker(c: Ctx) -> dict:
    # per broker: one aggregate doc and docs for the 3 heaviest topics
    b = KAFKA_BROKERS[c.i % 3]
    k = c.i // 3  # 0 = all topics, 1 = the heaviest topic
    d = host_doc("kafka/broker", b)
    topic = None if k == 0 else "clicks"
    scale = 1.0 if topic is None else TOPIC_W[topic] / 30
    kb = d["kafka"]
    kb.pop("topic", None) if topic is None else None
    name = "BytesInPerSec" if k % 2 else "BytesOutPerSec"
    kb["broker"] = {"id": b, "address": f"{BROKER_HOSTS[b]}:9092", "mbean": f"kafka.server:name={name},type=BrokerTopicMetrics" + (f",topic={topic}" if topic else "")}
    if topic:
        kb["topic"] = {"name": topic}
    rate = (35_000 + 480_000 * min(c.load, 1.5) / 1.5) * scale * (0.8 + 0.1 * b)
    r = c.rng
    kb["broker"].update({"messages_in": round(rate / 900, 3), "net": {"in": {"bytes_per_sec": round(rate, 2)}, "out": {"bytes_per_sec": round(rate * 2.4, 2)}, "rejected": {"bytes_per_sec": 0.0}},
                         "topic": {"messages_in": round(rate / 900 * 0.3, 3), "net": {"in": {"bytes_per_sec": round(rate * 0.3, 2)}, "out": {"bytes_per_sec": round(rate * 0.7, 2)}, "rejected": {"bytes_per_sec": 0.0}}},
                         "log": {"flush_rate": round(r.uniform(0.3, 2.2), 3)}, "request": {"channel": {"queue": {"size": r.randrange(0, 4)}}, "fetch": {"failed": 0, "failed_per_second": 0.0},
                                                                                             "produce": {"failed": 0, "failed_per_second": 0.0}},
                         "replication": {"leader_elections": 0.0, "unclean_leader_elections": 0.0}, "session": {"zookeeper": {"disconnect": 0.0, "expire": 0.0, "readonly": 0.0, "sync": 0.0}}})
    return infra.fill(d, "kafka/broker", c, only=("kafka.broker.error",))


def _topic_subs():
    """(group, topic, partition) triples in a stable order, one per consumer group subscription."""
    return [(g, t, p) for g, ts in KAFKA_GROUPS for t in ts for p in range(PARTS)]


SUBS = _topic_subs()


def _consumergroup(c: Ctx) -> dict:
    g, t, p = SUBS[(c.i * 2 + c.ts.minute // 10 % 2) % len(SUBS)]  # half of the subscriptions per 10 minute round
    lead = leader(t, p)
    d = host_doc("kafka/consumergroup", lead)
    r = c.rng
    produced = infra.counter(c.ts, TOPIC_W[t] * 0.25, f"off{t}{p}", False)
    # analytics-ingest lags under load, others keep up (small lag)
    lag = int(r.uniform(0, 30)) if g != "analytics-ingest" else int(max(0, r.gauss(900 * c.load, 300)))
    if g == "audit-writer" and t == "dead-letter":
        lag = int(infra.counter(c.ts, 0.0005, "dlq", False))
    d["kafka"] = {"broker": {"id": lead, "address": f"{BROKER_HOSTS[lead]}:9092"}, "topic": {"name": t}, "partition": {"id": p, "topic_id": f"{p}-{t}", "topic_broker_id": f"{lead}-{t}-{p}"},
                  "consumergroup": {"id": g, "client": {"id": f"{g}-{p}", "host": f"/10.20.6.{20 + infra.stable(g) % 30}", "member_id": f"{g}-{p}-{infra.stable(g, t, p):08x}"},
                                    "consumer_lag": lag, "offset": produced - lag, "error": {"code": 0}, "meta": ""}}
    return d


def _partition(c: Ctx) -> dict:
    t, p = PARTITIONS[(c.i * 2 + c.ts.minute // 10 % 2) % len(PARTITIONS)]  # half of the partitions per 10 minute round
    lead = leader(t, p)
    d = host_doc("kafka/partition", lead)
    newest = infra.counter(c.ts, TOPIC_W[t] * 0.25, f"off{t}{p}", False)
    d["kafka"] = {"broker": {"id": lead, "address": f"{BROKER_HOSTS[lead]}:9092"}, "topic": {"name": t, "error": {"code": 0}},
                  "partition": {"id": p, "topic_id": f"{p}-{t}", "topic_broker_id": f"{lead}-{t}-{p}", "offset": {"newest": newest, "oldest": max(0, newest - 600_000_000 // 100)},
                                "partition": {"insync_replica": True, "is_leader": True, "leader": lead, "replica": lead}}}
    return d


def _topic(c: Ctx) -> dict:
    t, p = PARTITIONS[(c.i + len(PARTITIONS) // 2 * (c.ts.minute // 10 % 2)) % len(PARTITIONS)]
    lead = leader(t, p)
    d = host_doc("kafka/topic", lead)
    r = c.rng
    end = infra.counter(c.ts, TOPIC_W[t] * 0.25, f"off{t}{p}", False)
    size = int(end * 620 % 6e9 + 4e7)
    d["kafka"]["topic"] = {"topic": {"name": t}, "partition": {"id": str(p), "at_min_isr": 0, "insync_replicas_count": 3, "replicas_count": 3, "under_min_isr": 0, "under_replicated": 0},
                           "log": {"end_offset": end, "start_offset": max(0, end - 6_000_000), "segments_count": 3 + size // 1_000_000_000, "size": size}}
    return infra.fill(d, "kafka/topic", c)


def _jvm(c: Ctx) -> dict:
    b = KAFKA_BROKERS[c.i % 3]
    v = c.i // 3
    d = host_doc("kafka/jvm", b)
    r = c.rng
    heap_max = 4 << 30
    used = int(heap_max * (0.25 + 0.3 * ((c.ts.timestamp() / 60 + b * 7) % 25) / 25 + 0.04 * c.load))  # sawtooth between GCs
    kj = d["kafka"]["jvm"]
    kj["memory"] = {"heap_usage": {"committed": heap_max, "init": heap_max // 4, "max": heap_max, "used": used}, "non_heap_usage": {"committed": 110_000_000, "init": 7_667_712, "max": -1, "used": 98_000_000 + r.randrange(0, 4_000_000)},
                    "objects_pending_finalization": 0}
    gcs = [("G1 Young Generation", 1.0), ("G1 Old Generation", 0.01)]
    gname, gw = gcs[v % 2]
    kj["gc"] = {"name": gname, "collection_count": infra.counter(c.ts, 0.1 * gw, f"gc{b}{v}", False), "collection_time_ms": infra.counter(c.ts, 6.0 * gw, f"gct{b}{v}", False)}
    kj["buffer_pool"] = {"name": ["direct", "mapped"][v % 2], "count": 20 + v * 3, "total_capacity": 80_000_000 + v * 5_000_000, "used": 78_000_000 + v * 5_000_000}
    pools = [("G1 Eden Space", "HEAP"), ("Metaspace", "NON_HEAP")]
    pn, pt = pools[v % 2]
    kj["memory_pool"] = {"name": pn, "type": pt, "mbean": f"java.lang:name={pn},type=MemoryPool"}
    kj["compilation"] = {"name": "HotSpot 64-Bit Tiered Compilers", "time_ms": infra.counter(c.ts, 4.0, f"jit{b}", False)}
    kj["runtime"] = {"name": f"{infra.stable(b) % 90000}@{BROKER_HOSTS[b]}", "vm_name": "OpenJDK 64-Bit Server VM", "vm_vendor": "Eclipse Adoptium", "vm_version": "17.0.12+7", "uptime_ms": int(c.ts.timestamp() * 1000) % 3_000_000_000}
    kj["classes"] = {"loaded_count": 9400 + b * 15, "total_loaded_count": 9500 + b * 15, "unloaded_count": 12}
    kj["threads"] = {"count": 70 + r.randrange(0, 8), "daemon_count": 62 + r.randrange(0, 4), "peak_count": 96, "total_started_count": 1200 + c.ts.minute}
    return infra.fill(d, "kafka/jvm", c, skip=("memory.heap", "memory.non_heap"))


def _controller(c: Ctx) -> dict:
    b = KAFKA_BROKERS[c.i % 3]
    d = host_doc("kafka/controller", b)
    active = 1 if b == 1 else 0
    kc = d["kafka"]["controller"] = {"kafka_controller": {"active_broker_count": 3 if active else 0, "active_controller_count": active, "fenced_broker_count": 0, "global_partition_count": len(PARTITIONS) if active else 0,
                                                          "global_topic_count": len(KAFKA_TOPICS) if active else 0, "offline_partitions_count": 0, "preferred_replica_imbalance_count": 0,
                                                          "metadata_error_count": 0, "timed_out_broker_heartbeat_count": 0}}
    return infra.fill(d, "kafka/controller", c, base=1.2 if active else 0.2)


def _log_manager(c: Ctx) -> dict:
    b = KAFKA_BROKERS[c.i % 3]
    d = host_doc("kafka/log_manager", b)
    lm = d["kafka"]["log_manager"] = {"directory_offline_count": {"value": 0, "log_directory": "/var/lib/kafka/data"}, "remaining_logs_to_recover": 0, "remaining_segments_to_recover": 0,
                                      "cleaner_manager": {"uncleanable_bytes": {"value": 0, "log_directory": "/var/lib/kafka/data"}, "uncleanable_partitions_count": {"value": 0, "log_directory": "/var/lib/kafka/data"},
                                                          "max_dirty_percent": int(c.rng.uniform(0, 12)), "time_since_last_run_ms": int(c.rng.uniform(1000, 280000))},
                                      "cleaner": {"dead_thread_count": 0, "max_buffer_utilization_percent": int(c.rng.uniform(1, 30)), "recopy_percent": int(c.rng.uniform(0, 40)), "max_compaction_delay_secs": 0}}
    return infra.fill(d, "kafka/log_manager", c)


REQ_TYPES = ["Produce", "FetchConsumer"]


def _network(c: Ctx) -> dict:
    b = KAFKA_BROKERS[c.i % 3]
    rt = REQ_TYPES[c.i // 3 % len(REQ_TYPES)]
    d = host_doc("kafka/network", b)
    d["kafka"]["network"] = {"acceptor_blocked": {"listener": "PLAINTEXT", "count": 0.0}, "processor_idle_percent": {"network_processor": str(b), "value": round(0.55 + 0.4 * (1 - c.load / 1.5), 4)},
                             "request_channel": {"response_queue_size": {"processor": str(b), "value": 0}, "request_queue_size": c.rng.randrange(0, 3)},
                             "request_metrics": {"request_type": rt, "error_type": "NONE"}, "socket_server": {"expired_connections_killed_count": 0}}
    n = d["kafka"]["network"]["request_metrics"]
    for m in ("temporary_memory_bytes", "total_time_ms", "throttle_time_ms", "local_time_ms", "response_queue_time_ms", "message_conversions_time_ms", "response_send_time_ms",
              "remote_time_ms", "request_queue_time_ms", "request_bytes"):
        n[m] = {"request_type": rt}
    base = {"Produce": 3.0, "FetchConsumer": 6.0}[rt]
    return infra.fill(d, "kafka/network", c, base=base)


def _producer(c: Ctx) -> dict:
    cid = ["order-service", "click-tracker"][c.i % 2]
    b = KAFKA_BROKERS[c.i % 3]
    d = host_doc("kafka/producer", b)
    r = c.rng
    d["kafka"]["producer"] = {"client_id": cid, "mbean": f"kafka.producer:type=producer-metrics,client-id={cid}", "node_id": f"node-{b}", "available_buffer_bytes": 33554432 - r.randrange(0, 1_000_000),
                              "batch_size_avg": int(r.uniform(900, 14000)), "batch_size_max": 16384, "io_wait": r.randrange(100_000_000, 900_000_000), "record_error_rate": 0.0, "record_retry_rate": round(r.uniform(0, 0.01), 4),
                              "record_send_rate": round(40 + 360 * c.load / 1.5 * r.uniform(0.9, 1.1), 3), "record_size_avg": int(r.uniform(180, 900)), "record_size_max": 4096, "records_per_request": round(r.uniform(2, 40), 2),
                              "request_rate": round(r.uniform(5, 60), 3), "response_rate": round(r.uniform(5, 60), 3), "out": {"bytes_per_sec": round(r.uniform(2e4, 9e5), 2)}}
    d["kafka"]["topic"] = {"name": "orders" if cid == "order-service" else "clicks"}
    d["kafka"]["broker"] = {"address": f"{BROKER_HOSTS[b]}:9092"}
    return infra.fill(d, "kafka/producer", c, only=("kafka.producer",))


def _consumer(c: Ctx) -> dict:
    cid = ["order-processor-1", "inventory-sync-1", "analytics-ingest-1"][c.i % 3]
    b = KAFKA_BROKERS[c.i % 3]
    d = host_doc("kafka/consumer", b)
    r = c.rng
    d["kafka"]["consumer"] = {"client_id": cid, "mbean": f"kafka.consumer:type=consumer-fetch-manager-metrics,client-id={cid}", "bytes_consumed": int(r.uniform(2e4, 9e5)), "fetch_rate": round(r.uniform(2, 40), 3),
                              "in": {"bytes_per_sec": round(r.uniform(2e4, 9e5), 2)}, "max_lag": int(r.uniform(0, 60)) if "analytics" not in cid else int(max(0, r.gauss(1100 * c.load, 300))),
                              "records_consumed": round(r.uniform(30, 400) * (0.4 + c.load), 2)}
    d["kafka"]["broker"] = {"address": f"{BROKER_HOSTS[b]}:9092"}
    d["kafka"]["topic"] = {"name": "orders"}
    return infra.fill(d, "kafka/consumer", c, only=("kafka.consumer",))


def _raft(c: Ctx) -> dict:
    b = KAFKA_BROKERS[c.i % 3]
    d = host_doc("kafka/raft", b)
    r = c.rng
    leader_id = 1
    state = "leader" if b == leader_id else "follower"
    off = infra.counter(c.ts, 3.5, "raft", False)
    d["kafka"]["raft"] = {"append_records_rate": round(r.uniform(0.3, 6), 3) if state == "leader" else 0.0, "commit_latency_avg": round(r.uniform(1, 9), 2), "commit_latency_max": round(r.uniform(9, 60), 2),
                          "current_epoch": 7, "current_leader": leader_id, "current_state": state, "current_vote": leader_id, "fetch_records_rate": round(r.uniform(0.3, 6), 3) if state == "follower" else 0.0,
                          "high_watermark": off, "log_end_epoch": 7, "log_end_offset": off, "number_of_voters": 3, "number_unknown_voter_connections": 0, "poll_idle_ratio_avg": round(r.uniform(0.85, 0.99), 4)}
    return infra.fill(d, "kafka/raft", c, only=("kafka.raft",))


def _replica_manager(c: Ctx) -> dict:
    b = KAFKA_BROKERS[c.i % 3]
    d = host_doc("kafka/replica_manager", b)
    r = c.rng
    own = sum(1 for t, p in PARTITIONS if leader(t, p) == b)
    d["kafka"]["replica_manager"] = {"leader_count": own, "partition_count": own * 3 // 1 // 1 if False else int(len(PARTITIONS) * 3 / 3), "offline_replica_count": 0, "at_min_isr_partition_count": 0,
                                     "under_min_isr_partition_count": 0, "under_replicated_partitions": 0, "reassigning_partitions": 0, "isr_expands_per_sec": {"one_minute_rate": 0.0}, "isr_shrinks_per_sec": {"one_minute_rate": 0.0},
                                     "failed_isr_updates_per_sec": {"one_minute_rate": 0.0}}
    if r.random() < 0.04:  # rare ISR flap
        d["kafka"]["replica_manager"]["isr_shrinks_per_sec"]["one_minute_rate"] = round(r.uniform(0.01, 0.1), 4)
    return infra.fill(d, "kafka/replica_manager", c)


LOGCLS = [("kafka.controller.KafkaController", "controller", "INFO", "[Controller id={b}] Processing automatic preferred replica leader election"),
          ("kafka.server.ReplicaFetcherThread", "replica-fetcher", "INFO", "[ReplicaFetcher replicaId={b}, leaderId=2, fetcherId=0] Partition {t}-{p} has an older epoch (6) than the current leader. Will await the new LeaderAndIsr state before resuming fetching."),
          ("kafka.log.LogCleaner", "kafka-log-cleaner-thread-0", "INFO", "Cleaner 0: Beginning cleaning of log {t}-{p}"),
          ("kafka.log.UnifiedLog", "kafka-scheduler-3", "INFO", "[UnifiedLog partition={t}-{p}, dir=/var/lib/kafka/data] Rolled new log segment at offset {off} in 3 ms."),
          ("kafka.coordinator.group.GroupCoordinator", "data-plane-kafka-request-handler-1", "INFO", "[GroupCoordinator {b}]: Preparing to rebalance group analytics-ingest in state PreparingRebalance with old generation 41 (reason: Adding new member)"),
          ("kafka.server.KafkaApis", "data-plane-kafka-request-handler-2", "WARN", "[KafkaApi-{b}] Unexpected error handling request RequestHeader(apiKey=FETCH) -- org.apache.kafka.common.errors.NotLeaderOrFollowerException"),
          ("org.apache.kafka.network.Processor", "data-plane-kafka-network-thread-{b}-ListenerName(PLAINTEXT)-PLAINTEXT-1", "ERROR", "[SocketServer listenerType=BROKER, nodeId={b}] Closing socket connection due to a network error: java.io.IOException: Connection reset by peer")]


def _log(c: Ctx) -> dict:
    r = c.rng
    b = r.choices(KAFKA_BROKERS, weights=[3, 2, 2])[0]
    cls, thread, lvl, tpl = r.choices(LOGCLS, weights=[3, 2, 3, 4, 1.5, 1, 0.6])[0]
    t, p = PARTITIONS[r.randrange(len(PARTITIONS))]
    msg = tpl.format(b=b, t=t, p=p, off=r.randrange(1_000_000, 90_000_000))
    ts = c.ts
    lines = [f"[{ts:%Y-%m-%d %H:%M:%S},{ts.microsecond // 1000:03d}] {lvl} {msg} ({cls})"]
    if lvl == "ERROR":
        lines.append("java.io.IOException: Connection reset by peer")
        lines.append("\tat java.base/sun.nio.ch.SocketDispatcher.read0(Native Method)")
        lines.append("\tat org.apache.kafka.common.network.SslTransportLayer.read(SslTransportLayer.java:615)")
    d = infra.log_base(BROKER_HOSTS[b], "/opt/kafka/logs/server.log")
    d["message"] = "\n".join(lines)
    d["service"] = {"type": "kafka"}
    d["event"] = {"timezone": "+00:00"}
    return d


# ---- Kafka Connect ---------------------------------------------------------------------------------------------------------------
WORKERS = ["connect-worker-1:8083", "connect-worker-2:8083"]
CONNECTORS = [("es-sink-orders", "io.confluent.connect.elasticsearch.ElasticsearchSinkConnector", "sink"), ("jdbc-source-customers", "io.confluent.connect.jdbc.JdbcSourceConnector", "source"),
              ("s3-sink-clicks", "io.confluent.connect.s3.S3SinkConnector", "sink")]


def _kc_doc(key: str, i: int) -> dict:
    w = WORKERS[i % 2]
    d = infra.metric_base(key, w.split(":")[0], module="kafka")
    d["service"] = {"address": w, "type": "kafka"}
    d["host"]["name"] = w.split(":")[0]
    return d


def _kc_client(c: Ctx) -> dict:
    d = _kc_doc("kafka_connect/client", c.i)
    cid = ["connector-consumer-es-sink-orders-0", "connector-producer-jdbc-source-customers-0"][c.i % 2]
    d["kafka_connect"]["client"] = {"id": cid}
    d["kafka_connect"]["mbean"] = f"kafka.connect:client-id={cid},type=connect-metrics"  # the package pipeline dissects the client id from the mbean
    return infra.fill(d, "kafka_connect/client", c, zeros=True)


def _kc_connector(c: Ctx) -> dict:
    name, cls, typ = CONNECTORS[c.i % 3]
    d = _kc_doc("kafka_connect/connector", c.i)
    d["kafka_connect"]["connector"] = {"name": name, "class": cls, "type": typ, "version": "14.1.2", "status": "running"}
    d["kafka_connect"]["mbean"] = f"kafka.connect:connector={name},type=connector-metrics"  # pipeline dissects connector.name from it
    return infra.fill(d, "kafka_connect/connector", c, zeros=True)


def _kc_task(c: Ctx) -> dict:
    name, cls, typ = CONNECTORS[c.i % 3]
    d = _kc_doc("kafka_connect/task", c.i)
    d["kafka_connect"]["connector"] = {"name": name}
    d["kafka_connect"]["task"] = {"id": "0", "status": "running"}
    d["kafka_connect"]["mbean"] = f"kafka.connect:connector={name},task=0,type=connector-task-metrics"
    return infra.fill(d, "kafka_connect/task", c, zeros=True)


def _kc_worker(c: Ctx) -> dict:
    d = _kc_doc("kafka_connect/worker", c.i)
    d["kafka_connect"]["worker"] = {"address": WORKERS[c.i % 2]}
    return infra.fill(d, "kafka_connect/worker", c, zeros=True)


registry.register(
    GROUP,
    Generator(S["kafka/broker"], _broker, mode="entities", entities=6, every_min=10),
    Generator(S["kafka/consumergroup"], _consumergroup, mode="entities", entities=(len(SUBS) + 1) // 2, every_min=10),
    Generator(S["kafka/partition"], _partition, mode="entities", entities=len(PARTITIONS) // 2, every_min=10),
    Generator(S["kafka/topic"], _topic, mode="entities", entities=len(PARTITIONS) // 2, every_min=10),
    Generator(S["kafka/jvm"], _jvm, mode="entities", entities=6, every_min=10),
    Generator(S["kafka/controller"], _controller, mode="entities", entities=3, every_min=10),
    Generator(S["kafka/log_manager"], _log_manager, mode="entities", entities=3, every_min=10),
    Generator(S["kafka/network"], _network, mode="entities", entities=6, every_min=10),
    Generator(S["kafka/producer"], _producer, mode="entities", entities=2, every_min=5),
    Generator(S["kafka/consumer"], _consumer, mode="entities", entities=3, every_min=10),
    Generator(S["kafka/raft"], _raft, mode="entities", entities=3, every_min=10),
    Generator(S["kafka/replica_manager"], _replica_manager, mode="entities", entities=3, every_min=10),
    Generator(S["kafka/log"], _log, rate_per_min=1.2),
    Generator(S["kafka_connect/client"], _kc_client, mode="entities", entities=2, every_min=10),
    Generator(S["kafka_connect/connector"], _kc_connector, mode="entities", entities=3, every_min=10),
    Generator(S["kafka_connect/task"], _kc_task, mode="entities", entities=3, every_min=10),
    Generator(S["kafka_connect/worker"], _kc_worker, mode="entities", entities=2, every_min=10),
)
