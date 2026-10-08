"""Deterministic generation, bulk writing and gap-healing state.

Idempotency: a document's `_id` is sha1(stream, minute, index). Event counts per minute come from a seeded RNG, so
generating the same window twice yields the same ids and the second bulk (op `create`) answers 409 (ignored).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Iterator

from . import profile
from .registry import Ctx, Generator

UTC = timezone.utc
TAGS = ["synthetic", "synthetic-data-feeder"]
STATE_INDEX = "synthetic-data-feeder-state"
MAX_HEAL = timedelta(days=7)
BATCH = 500


def doc_id(stream_key: str, minute: datetime, i: int) -> str:
    return hashlib.sha1(f"{stream_key}|{int(minute.timestamp())}|{i}".encode()).hexdigest()[:20]  # noqa: S324


def tag(doc: dict) -> dict:
    """Mark a document synthetic: tags (appended) and labels.synthetic."""
    t = doc.get("tags")
    cur = [t] if isinstance(t, str) else list(t or [])
    doc["tags"] = cur + [x for x in TAGS if x not in cur]
    labels = doc.get("labels") if isinstance(doc.get("labels"), dict) else {}
    doc["labels"] = {**labels, "synthetic": "true"}
    return doc


def minutes(start: datetime, end: datetime) -> Iterator[datetime]:
    m = profile.minute_floor(start)
    if m < start:
        m += timedelta(minutes=1)
    while m < end:
        yield m
        m += timedelta(minutes=1)


def generate(g: Generator, start: datetime, end: datetime) -> Iterator[tuple[str, dict]]:
    """Yield (_id, document) for every event whose minute bucket lies in [start, end)."""
    s = g.stream
    for m in minutes(start, end):
        rng = profile.rng_for(s.key, int(m.timestamp()))
        load = profile.activity(m)
        if g.mode == "entities":
            if (int(m.timestamp()) // 60) % g.every_min:
                continue
            n = g.entities
        else:
            n = profile.poisson(rng, g.rate_per_min * load)
            if n == 0 and (int(m.timestamp()) // 60) % 10 == 0:
                n = 1  # trickle: quiet streams still show an event at least every 10 minutes (no STALE dashboards at night)
        for i in range(n):
            drng = profile.rng_for(s.key, int(m.timestamp()), i)
            ts = m + timedelta(seconds=drng.uniform(0, 59.9)) if g.mode == "events" else m
            doc = g.build(Ctx(s, ts, i, drng, load))
            doc["@timestamp"] = profile.iso(ts)  # always: templates carry the sample's old timestamp
            # like Elastic Agent: constant_keyword data_stream.* fields only take a value from the first document
            doc.setdefault("data_stream", {"type": s.type, "dataset": s.dataset, "namespace": "default"})
            if not s.dataset.endswith(".otel"):  # event.dataset is a field alias in OTel mappings (not writable)
                doc.setdefault("event", {}).setdefault("dataset", s.dataset)
            yield doc_id(s.key, m, i), tag(doc)


NO_ID_PREFIXES: list[str] = []  # index prefixes of TSDB data streams (gen modules append), see is_tsdb


def is_tsdb(index: str) -> bool:
    """TSDB data streams (OTel metrics and most integration metrics) refuse a custom _id: it is derived from the
    dimensions and the timestamp, so a repeated document answers 409 as well. Gen modules register their prefixes."""
    return (index.startswith("metrics-") and ".otel-" in index) or any(index.startswith(p) for p in NO_ID_PREFIXES)


def bulk_lines(index: str, docs: list[tuple[str, dict]]) -> list[dict]:
    out: list[dict] = []
    tsdb = is_tsdb(index)
    for _id, d in docs:
        meta = {"_index": index} if tsdb else {"_index": index, "_id": _id}
        dyn = d.pop("_dynamic_templates", None)  # OTel metrics: field path -> counter_long / gauge_double ... (mapped like the OTLP endpoint does)
        if dyn:
            meta["dynamic_templates"] = dyn
        out.append({"create": meta})
        out.append(d)
    return out


def write(client, index: str, docs: list[tuple[str, dict]]) -> dict:
    """Bulk `create` in batches of BATCH; 409 conflicts are counted, not errors."""
    res = {"created": 0, "conflicts": 0, "errors": 0, "error_sample": ""}
    for i in range(0, len(docs), BATCH):
        st, body = client.bulk(bulk_lines(index, docs[i:i + BATCH]))
        if st != 200 or not isinstance(body, dict):
            res["errors"] += len(docs[i:i + BATCH])
            res["error_sample"] = f"http {st} {str(body)[:200]}"
            continue
        for it in body.get("items", []):
            r = it.get("create", {})
            s = r.get("status", 0)
            if r.get("failure_store") == "used":  # indexing failed (mapping/pipeline): the doc went to the failure store
                res["errors"] += 1
                res["error_sample"] = res["error_sample"] or "document went to the failure store (see ::failures)"
            elif s in (200, 201):
                res["created"] += 1
            elif s == 409:
                res["conflicts"] += 1
            else:
                res["errors"] += 1
                res["error_sample"] = res["error_sample"] or f"{s} {r.get('error', {}).get('type')}: {str(r.get('error', {}).get('reason'))[:160]}"
    return res


# --- state (index synthetic-data-feeder-state, one document per stream) -------------------------------------------

def get_state(client, key: str) -> datetime | None:
    st, body = client.es("GET", f"/{STATE_INDEX}/_doc/{_state_id(key)}")
    if st == 200 and isinstance(body, dict) and body.get("found"):
        return datetime.fromisoformat(body["_source"]["last_covered"].replace("Z", "+00:00"))
    return None


def put_state(client, key: str, ts: datetime) -> int:
    body = {"stream": key, "last_covered": profile.iso(ts), "updated": profile.iso(datetime.now(UTC))}
    st, _ = client.es("PUT", f"/{STATE_INDEX}/_doc/{_state_id(key)}", body)
    return st


def _state_id(key: str) -> str:
    return key.replace("/", "__")


def ensure_state_index(client) -> int:
    st, _ = client.es("PUT", f"/{STATE_INDEX}", {"mappings": {"properties": {
        "stream": {"type": "keyword"}, "last_covered": {"type": "date"}, "updated": {"type": "date"}}}})
    return st  # 200 created, 400 already exists (fine)


def plan_window(last: datetime | None, now: datetime, window_minutes: int) -> tuple[datetime, datetime]:
    """Window to cover: [last covered, now). First run covers `window_minutes`; gaps heal up to 7 days."""
    end = profile.minute_floor(now)
    start = last if last else end - timedelta(minutes=window_minutes)
    return max(start, end - MAX_HEAL), end


def tick(client, gens: list[Generator], now: datetime, window_minutes: int = 5, max_docs: int = 5000,
         chunk: timedelta = timedelta(hours=2), log=print) -> dict:
    """Cover [last covered, now) for every generator, advancing state after each chunk. Stops at the doc cap."""
    ensure_state_index(client)
    total = {"created": 0, "conflicts": 0, "errors": 0}
    budget = max_docs
    for g in gens:
        last = get_state(client, g.stream.key)
        start, end = plan_window(last, now, window_minutes)
        cur = start
        while cur < end and budget > 0:
            nxt = min(cur + chunk, end)
            docs = list(generate(g, cur, nxt))
            capped = False
            if len(docs) > budget and docs:
                capped = True  # cap: keep whole minutes only so state stays consistent
                docs = docs[:budget]
                nxt = profile.minute_floor(datetime.fromisoformat(docs[-1][1]["@timestamp"].replace("Z", "+00:00")))
                docs = [d for d in docs if datetime.fromisoformat(d[1]["@timestamp"].replace("Z", "+00:00")) < nxt]
            r = write(client, g.stream.index, docs) if docs else {"created": 0, "conflicts": 0, "errors": 0, "error_sample": ""}
            for k in total:
                total[k] += r[k]
            budget = 0 if capped else budget - len(docs)
            if r["errors"]:
                log(f"{g.stream.key}: {r['errors']} errors ({r['error_sample']})")
                break  # do not advance state past failed writes
            put_state(client, g.stream.key, nxt)
            cur = nxt
    total["remaining_budget"] = budget
    return total
