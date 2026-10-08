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
