"""CLI: python -m feeder <command>   (see docs/feeder.md)

Runtime (CronJob):  tick           uses ONLY env OBS_ES_URL and FEEDER_KEY (narrow write-only key)
Local (admin key):  install, harvest, backfill, coverage, cleanup, simulate, list
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import catalog, engine, profile, registry

UTC = timezone.utc


def _admin():
    from .es import AdminClient
    return AdminClient()


def _gens(group: str):
    gs = registry.generators(group)
    if not gs:
        sys.exit(f"no generators for group {group!r}; groups: {', '.join(registry.groups())}")
    return gs


def cmd_list(a) -> int:
    registry.load_all()
    for g in registry.groups():
        print(f"group {g}")
        for p in catalog.packages(g):
            print(f"  {p.name} {p.version}: " + ", ".join(s.dir for s in p.streams))
        gens = registry.generators(g)
        per_min = sum(x.rate_per_min if x.mode == "events" else x.entities / x.every_min for x in gens)
        print(f"  generators: {len(gens)}, about {per_min:.1f} docs/min at load 1.0")
    return 0


def cmd_install(a) -> int:
    registry.load_all()
    c = _admin()
    rc = 0
    for p in catalog.packages(a.group):
        st, body = c.kb("POST", f"/api/fleet/epm/packages/{p.name}/{p.version}", {"force": False})
        ok = st == 200
        rc |= 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {p.name} {p.version} (http {st})" + ("" if ok else f" {str(body)[:160]}"))
    return rc


def cmd_harvest(a) -> int:
    from . import harvest
    registry.load_all()
    out = harvest.harvest(_admin().kb, a.group)
    print("\n".join(out))
    return 1 if any(x.startswith("MISSING") for x in out) else 0


def cmd_backfill(a) -> int:
    c = _admin()
    now = datetime.now(UTC)
    start = profile.minute_floor(now) - timedelta(days=a.days)
    end = profile.minute_floor(now)
    engine.ensure_state_index(c)
    budget, tot = a.max_docs, {"created": 0, "conflicts": 0, "errors": 0}
    for g in _gens(a.group):
        n_stream = 0
        cur = start
        while cur < end and budget > 0:
            nxt = min(cur + timedelta(hours=6), end)
            docs = list(engine.generate(g, cur, nxt))
            if len(docs) > budget:
                docs = docs[:budget]
            r = engine.write(c, g.stream.index, docs) if docs else {"created": 0, "conflicts": 0, "errors": 0, "error_sample": ""}
            for k in tot:
                tot[k] += r[k]
            n_stream += len(docs)
            budget -= len(docs)
            if r["errors"]:
                print(f"{g.stream.key}: {r['errors']} errors: {r['error_sample']}")
                break
            cur = nxt
        else:
            engine.put_state(c, g.stream.key, cur)
        print(f"{g.stream.key}: {n_stream} docs")
    print(json.dumps(tot))
    return 1 if tot["errors"] else 0


def cmd_tick(a) -> int:
    from .es import KeyClient, MissingKey, local_feeder_client
    try:
        c = local_feeder_client() if a.local_key else KeyClient.from_env()
    except MissingKey as e:
        print(f"feeder tick: {e}", file=sys.stderr)
        return 2
    res = engine.tick(c, _gens(a.group), datetime.now(UTC), a.window_minutes, a.max_docs)
    print("feeder tick: " + json.dumps(res))
    return 1 if res["errors"] else 0


def cmd_coverage(a) -> int:
    from . import coverage
    registry.load_all()
    c = _admin()
    only = None if a.group == "all" else {p.name for p in catalog.packages(a.group)}
    report = coverage.evaluate(c.es, coverage.load_dashboards(c.kb, only))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(report, f, indent=1)
        print(f"wrote {a.json}")
    print(coverage.render(report, verbose=a.verbose))
    return 0


def cmd_cleanup(a) -> int:
    registry.load_all()
    c = _admin()
    gens = _gens(a.group)
    q = {"query": {"term": {"tags": "synthetic-data-feeder"}}}
    for g in gens:
        if a.stream and g.stream.key != a.stream:
            continue
        st, body = c.es("POST", f"/{g.stream.type}-{g.stream.dataset}-*/_delete_by_query?conflicts=proceed&refresh=true&ignore_unavailable=true&allow_no_indices=true", q)
        deleted = body.get("deleted") if isinstance(body, dict) else body
        print(f"{g.stream.key}: http {st} deleted {deleted}")
        c.es("POST", f"/{g.stream.index}::failures/_delete_by_query?conflicts=proceed&refresh=true",  # failed synthetic docs
             {"query": {"term": {"document.source.tags": "synthetic-data-feeder"}}})
        c.es("DELETE", f"/{engine.STATE_INDEX}/_doc/{engine._state_id(g.stream.key)}")  # re-generate from scratch next time
    return 0


def cmd_simulate(a) -> int:
    """Run generated raw documents through each stream's ingest pipeline (_simulate) and report errors."""
    registry.load_all()
    c = _admin()
    now = datetime.now(UTC)
    rc = 0
    for g in _gens(a.group):
        s = g.stream
        if (a.stream and s.key != a.stream) or s.key == "azure_openai/billing" or getattr(s, "no_pipeline", False):
            continue  # billing and the OTel content streams (infra group) have no package pipeline
        docs = []
        for t in range(0, 600, 1):
            docs = [d for _, d in engine.generate(g, now - timedelta(minutes=t + 5), now - timedelta(minutes=t))]
            if len(docs) >= a.n:
                break
        docs = docs[:a.n] or [d for _, d in engine.generate(g, now - timedelta(days=1), now)][:a.n]
        if not docs:
            print(f"{s.key}: no documents generated")
            rc = 1
            continue
        st, body = c.es("POST", f"/_ingest/pipeline/{s.pipeline}/_simulate", {"docs": [{"_source": d} for d in docs]})
        if st != 200:
            print(f"{s.key}: simulate http {st} {str(body)[:200]}")
            rc = 1
            continue
        errs = []
        for r in body["docs"]:
            if "error" in r:
                errs.append(str(r["error"])[:200])
            elif not r.get("doc"):
                errs.append("dropped by pipeline")
            elif r["doc"]["_source"].get("error", {}).get("message"):
                errs.append(str(r["doc"]["_source"]["error"]["message"])[:200])
        print(f"{s.key}: {len(docs)} docs, {len(errs)} errors" + (f" e.g. {errs[0]}" if errs else ""))
        if a.show and body["docs"] and body["docs"][0].get("doc"):
            print(json.dumps(body["docs"][0]["doc"]["_source"])[:a.show])
        rc |= 1 if errs else 0
    return rc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="feeder", description="synthetic-data-feeder: fills OOTB integration dashboards with tagged synthetic data")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, group_default="all"):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--group", default=group_default)
        sp.set_defaults(fn=fn)
        return sp

    add("list", cmd_list, "show groups, packages, generators")
    add("install", cmd_install, "install the group's Fleet packages (assets only; admin key)")
    add("harvest", cmd_harvest, "fetch sample_event.json templates from Fleet (admin key)")
    b = add("backfill", cmd_backfill, "generate history in bulk (admin key)")
    b.add_argument("--days", type=int, default=7)
    b.add_argument("--max-docs", type=int, default=400000)
    t = add("tick", cmd_tick, "generate [last covered, now) with env OBS_ES_URL + FEEDER_KEY (CronJob)")
    t.add_argument("--window-minutes", type=int, default=5)
    t.add_argument("--max-docs", type=int, default=5000)
    t.add_argument("--local-key", action="store_true", help="local test: use OBSERVABILITY_FEEDER_API_KEY from elasticsearch.txt")
    c = add("coverage", cmd_coverage, "dashboard coverage report (admin key)")
    c.add_argument("--json", help="write the full report as JSON to this path")
    c.add_argument("-v", "--verbose", action="store_true")
    k = add("cleanup", cmd_cleanup, "delete ONLY documents tagged synthetic-data-feeder (admin key)")
    k.add_argument("--stream", help="limit to one stream key, e.g. openai/completions")
    s = add("simulate", cmd_simulate, "dev: run generated docs through the ingest pipelines (admin key)")
    s.add_argument("--stream")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--show", type=int, default=0)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
