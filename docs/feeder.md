# synthetic-data-feeder

Keeps the out-of-the-box (OOTB) dashboards of Elastic integrations filled with realistic SYNTHETIC data, without
setting up the real integrations. Every document is tagged, so it can be filtered out or deleted in one step.

Honesty note: this data is made up. Say so in any demo or screenshot that shows these dashboards. It lives in the same
Observability project as the real LLM Observability data, in the data streams of the integration packages
(for example `logs-openai.completions-default`), and never in the app's own indices.

## Why

OOTB integration dashboards are empty until a real agent ships that integration's data. The feeder installs the
package assets only (no agent policies, no package policies), writes synthetic documents into the packages' own
data streams, and a CronJob keeps them fresh and heals gaps (outages) by itself.

## Separate synthetic from real data

Every synthetic document has `tags: ["synthetic", "synthetic-data-feeder", ...existing tags]` and
`labels.synthetic: "true"`.

* Hide it in Discover or a dashboard: KQL `not tags: synthetic`
* Show only it: KQL `tags: synthetic` (or `tags: synthetic-data-feeder`)
* ES|QL: `WHERE NOT (tags == "synthetic")`

## How it works

* `backend/feeder/` is a Python package (also in the app image). Generators are deterministic: the number of events per
  minute comes from a seeded RNG (profile: day and night, weekday and weekend, a slow wave, per user / model / org
  distributions, 1 to 3 percent errors, correlated tokens, cost and latency). The `_id` is derived from stream,
  minute and index and bulk uses the `create` op, so repeating a window answers 409 which is ignored: ticks are idempotent.
* Log streams are sent RAW (`message` with the JSON text, or OTel shaped attributes for claude_code) and the package's own
  ingest pipeline parses them (check with `python -m feeder simulate`). Metric streams are final shaped documents.
* Templates (`backend/feeder/templates/<package>/<stream>.json`) are the packages' `sample_event.json`, fetched once with
  `harvest` and committed, so runtime needs no Fleet access. (Pipeline test inputs under `_dev` are not served by Fleet.)
* State: one document per stream in index `synthetic-data-feeder-state` holds the last covered timestamp. The CronJob
  needs no search or read privilege on data indices. Each tick covers `[last covered, now)`; after an outage it heals
  up to 7 days, at most `--max-docs` (default 5000) documents per run, oldest first, continuing on the next run.
* Quiet streams still emit an event at least every 10 minutes, so no dashboard goes STALE at night.

## Commands

Run from `backend/` (`source .venv/bin/activate`). Admin commands read the admin key through `elastic/client.py`.

| Command | Key | What |
|---|---|---|
| `python -m feeder list` | none | groups, packages, generators and rate |
| `python -m feeder install --group ai` | admin | install the Fleet package assets (nothing else) |
| `python -m feeder harvest --group ai` | admin | refresh the sample templates from Fleet |
| `python -m feeder simulate --group ai [--stream k]` | admin | run generated raw docs through each ingest pipeline (_simulate) and report errors |
| `python -m feeder backfill --days 7 --group ai [--max-docs 200000]` | admin | bulk history, also sets the state |
| `python -m feeder tick --group all --window-minutes 5` | feeder | the CronJob command (env `OBS_ES_URL`, `FEEDER_KEY`) |
| `python -m feeder tick ... --local-key` | feeder | local test with `OBSERVABILITY_FEEDER_API_KEY` from elasticsearch.txt |
| `python -m feeder coverage [--group g\|all] [--json path] [-v]` | admin | dashboard coverage report |
| `python -m feeder cleanup [--group g] [--stream k]` | admin | delete ONLY documents tagged `synthetic-data-feeder` (and reset state) |

`tick` fails with exit code 2 and a clear message when `OBS_ES_URL` or `FEEDER_KEY` is missing. Keys are never printed or logged.

## Coverage report

`coverage` resolves the panels of every dashboard of every installed package (lens by value and by reference, legacy
visualizations incl. TSVB, saved searches, ES|QL, maps; classic and inline panels), applies dashboard and panel
filters and queries, and checks for the last 15 minutes and 7 days that the data views have documents and every
referenced field is populated. Status per dashboard: EMPTY (no panel populated in 7 days), PARTIAL (some), STALE
(all populated in 7 days, none in the last 15 minutes), FILLED, NO_DATA (only markdown or controls). Column filters inside
formulas are not applied.

## Creating the feeder key (once, Dev Tools in the Observability project)

The key is named `synthetic-data-feeder`, has no expiration and can only create documents:

```
POST /_security/api_key
{
  "name": "synthetic-data-feeder",
  "role_descriptors": {
    "synthetic-data-feeder": {
      "indices": [
        { "names": ["logs-*", "metrics-*", "traces-*"], "privileges": ["create_doc", "auto_configure", "create_index"] },
        { "names": ["synthetic-data-feeder-state"], "privileges": ["create_index", "auto_configure", "read", "write"] }
      ]
    }
  }
}
```

Put the `encoded` value in the gitignored `elasticsearch.txt` as `OBSERVABILITY_FEEDER_API_KEY=...`. For the cluster,
`deploy/scripts/create_secrets.sh` writes it to Secret `glassbox-app` key `feeder_key` from, in order: env `FEEDER_KEY`,
`elasticsearch.txt` `OBSERVABILITY_FEEDER_API_KEY`, or the gitignored file `backend/secrets/feeder_key.txt`
(skipped with a note when none exists). The CronJob reads `OBS_ES_URL` from key `obs_es_url` and `FEEDER_KEY` from
`feeder_key` (optional, so the app is unaffected; the job fails clearly without it).

## Deploy

CronJob `synthetic-data-feeder` (`deploy/k8s/56-feeder.yaml`, namespace genai-demo): `*/5 * * * *`, concurrencyPolicy
Forbid, startingDeadlineSeconds 120, activeDeadlineSeconds 240, hardened like the traffic generator. `deploy.sh`
applies it, NOT suspended, and `demo_down.sh` deliberately does not suspend it. Pause: `kubectl -n genai-demo patch
cronjob synthetic-data-feeder -p '{"spec":{"suspend":true}}'`. The image must contain `backend/feeder` (Dockerfile copies it).

## Budget

Stage 1 (AI group): about 13 documents per minute at peak load, roughly 45 per 5 minute tick on average (hard
target below 400 per tick; the group is capped by the per run limit of 5000). A 7 day backfill is about 90 thousand
documents. Expect roughly 10 to 30 MB per day for the group (claude_code keeps `event.original`). All stages together
stay under about 1500 documents per tick.

## Extending: add a group (stages 2 and 3)

1. Create `backend/feeder/gen/<group>.py`. Modules in `feeder/gen/` are discovered automatically.
2. Declare packages with `catalog.register(catalog.pkg(name, version, group, [(data_stream_dir, dataset, type), ...]))`.
   The dir is the package `data_stream` path (may differ from the dataset suffix).
3. Write build functions `build(ctx) -> dict` (`registry.Ctx`: stream, ts, i, rng, load) and register
   `registry.register("<group>", Generator(stream, build, rate_per_min=..., mode="events"|"entities", entities=n, every_min=m))`.
   Logs: return the RAW event (so the package pipeline parses it); metrics: the final shaped document. Use `feeder.profile`
   for activity, users, tokens, cost and latency. Do not set `@timestamp`, tags or `data_stream`: the engine does.
4. Run `harvest --group <group>`, `install --group <group>`, `simulate --group <group>` (no `error.message`),
   `backfill --days 7 --group <group>`, then `coverage --group <group> -v` and iterate until FILLED.
5. Add offline tests like `backend/tests/test_feeder_core.py`.

## Known limits

* Four Claude Code dashboards (MCP Server Access, Permission Decisions, Security Overview, Tool Call Analysis) have
  panels filtering on unprefixed fields (`decision`, `decision_source`, `status`, `success`) that no mapping defines
  and the package pipeline never produces; they stay PARTIAL with real data too.
* The Anthropic audit dashboard has a panel that counts pipeline errors (`error.message exists`); it stays empty by design.
* Documents whose indexing fails go to the data stream failure store; the feeder counts them as errors and does not
  advance the state.

## Remove everything synthetic

`python -m feeder cleanup --group all` (admin key) deletes only documents tagged `synthetic-data-feeder` and resets the
state. Packages stay installed. To stop new data: suspend the CronJob.

## Group infra: nginx, windows, redis, mysql, kafka (stage 2)

Group name `infra`, 56 data streams, 14 packages, 47 dashboards. Everything is generated by `backend/feeder/gen/infra*.py`.
`python -m feeder backfill --days 7 --group infra` writes about 304 thousand documents (the default `--max-docs` is now 400000), a normal 5 minute
tick is about 150 documents on average and stays under 400 at the busiest time of day (checked by `tests/test_feeder_infra.py`).

| Package | Streams | What is generated |
|---|---|---|
| `nginx` | access, error, stubstatus | 3 hosts (`web-sin-01..03`), raw combined access lines with a realistic status, path and user agent mix (2 percent errors), upstream errors, stubstatus counters |
| `nginx_ingress_controller` | access, error | one ingress controller, three upstream services, raw ingress log lines, glog style errors |
| `windows` | all 11 streams | 5 hosts (`WIN-AD01`, `WIN-FS01`, `WIN-APP01`, `WIN-SQL01`, `WIN-WKS07`): services (one flaky service, one manual start service), perfmon, AppLocker (4 streams, incl. packaged apps), PowerShell classic and operational (4103 sent as raw ContextInfo and Payload), Sysmon (1, 3, 7, 11, 13, 22), Defender, forwarded Security (4624, 4625, 4672, 4688, 4768, 4720) |
| `redis` | info, key, keyspace, log, slowlog | `redis-cache-01` (master) and `redis-cache-02` (replica), db0 and db1, counters grow with the load, raw server log lines and slowlog entries on the master |
| `redisenterprise` | node, proxy | 3 nodes, 2 databases (`orders-cache`, `session-store`) |
| `mysql` | status, performance, replica_status, galera_status, slowlog, error | `mysql-primary-01` and replicas `mysql-replica-01/02`, the replica status is sent as raw `sql.metrics.*` (the package pipeline renames it), raw multi line slow log entries, galera status for the same 3 nodes |
| `kafka` | 12 metric streams, log | 3 brokers, 12 topics (1 partition, replication factor 3), 5 consumer groups (one lags under load), 2 producers, a KRaft quorum; JVM, network, log manager, controller, replica manager |
| `kafka_connect` | client, connector, task, worker | 2 workers, 3 connectors (`kafka_connect.mbean` is sent in the Jolokia format because the pipeline derives the names from it) |
| `nginx_otel`, `nginx_ingress_controller_otel`, `redis_otel`, `redisenterprise_otel`, `mysql_otel`, `kafka_otel` | OTel streams | see below |

### OpenTelemetry content packages

Direct writes into `metrics-*.otel-*` and `logs-*.otel-*` work, no OTLP fallback is needed. What makes it work (all probed on the live project):

* The OTel metrics data streams are time series data streams: no custom `_id` is allowed (the engine drops it for them, repeats give
  409 on the id Elasticsearch derives from dimensions and timestamp). Most integration metric streams (nginx stubstatus, kafka, redis,
  mysql, windows service) are time series too; the engine knows them (`engine.NO_ID_PREFIXES`, registered by `gen/infra.py`). Every generated
  document therefore needs distinct dimensions per timestamp; `tests/test_feeder_infra.py` checks that with the dimension lists in `templates/infra_dims.json`.
* Documents have the shape of the Elastic OTLP endpoint output: `metrics.<name>`, `attributes`, `resource.attributes`, `scope`, `_metric_names_hash`.
  The counter or gauge mapping of every metric is set through bulk `dynamic_templates` hints (`_dynamic_templates` on the document, moved to
  the bulk action by the engine; kinds in `templates/otel_metric_kinds.json`) so `RATE()` in ES|QL TS queries works.
* The OTel mappings have no top level `tags`. The tag is carried as `resource.attributes.tags` (a time series dimension) and `resource.attributes.labels.synthetic`,
  which the passthrough mapping exposes as `tags` and `labels.synthetic`. KQL `tags: synthetic` and `not tags: synthetic` work; in ES|QL use
  `labels.synthetic == "true"` (a multi valued `tags` does not compare with `==`). `cleanup` finds these documents too.
* Series are written to the namespace `synthetic` (`metrics-redisreceiver.otel-synthetic`, ...) so they never mix with the real collector data that already lives in
  `metrics-redisreceiver.otel-default` and `metrics-kafkametricsreceiver.otel-default` of the same project. The dashboards read `metrics-*` and filter on
  `data_stream.dataset`, so both show up. Exception: the Redis Enterprise OTel dashboards read exactly `metrics-redisenterprise.otel-default`, so that package uses the `default` namespace.
* The first backfill creates the OTel data streams. A time series data stream accepts documents from 7 days before its creation, so the first
  minutes of a first `backfill --days 7` can answer `timestamp_error` and the command stops after that chunk: run it a second time (idempotent, only the rest is written).

### Known unfillable panels

* `[Logs Kafka] Overview`: one panel reads `kafka.log.trace.full`; the package pipeline removes that field after extracting the trace class and message.
* `[MySQL OTel] Queries`: four panels (Active Queries and the wait summary) read query samples of `NOW() - 1 minute`. The feeder writes in batches of 5 minutes, so there is never a record in the last minute.
* `[Windows powershell] Overview`: the panel `Engine and Command started` has two filters (`event.code` 400 and 4105) that are separate columns in the dashboard; `coverage` applies them together, so it can never count it.
* The TSDB integration streams are written every 10 minutes (every 20 for perfmon and galera, which have no dashboard); counters grow with the load profile, so `RATE()` panels show a day/night shape but not second level detail.
* `nginx_otel_input`, `nginx_ingress_controller_otel` inputs, `redis_input_otel`, `mysql_input_otel`, `kafka_input_otel`, `kafka_log`, `windows_etw`, `mysql_enterprise`: input packages with no dashboards, not generated.

### Operating the group

```
python -m feeder install --group infra       # 14 packages (assets only)
python -m feeder backfill --days 7 --group infra
python -m feeder coverage --group infra -v   # 44 FILLED, 3 PARTIAL of 47 (reasons above)
python -m feeder tick --group infra --local-key
```

The narrow feeder key (`create_doc` on `logs-*` and `metrics-*`) is enough for every stream of the group; no index pattern is denied.
`coverage` got one fix: legacy saved filters `{"match": {field: {"query": v, "type": "phrase"}}}` (Windows services dashboard) are converted to `match_phrase`,
because current Elasticsearch rejects them and the panel looked empty.
