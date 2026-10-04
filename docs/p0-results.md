# Phase 0 spike results (2026-10-04)

No secrets in this file. Evidence scripts: `scripts/spikes/`.

## A. Gemini model IDs (Vertex AI, project elastic-sa)

Spike: `scripts/spikes/gemini_ids.py` ("Reply with the single word: pong").

| model | global | asia-southeast1 |
|---|---|---|
| gemini-3.1-flash-lite | OK | 404 NOT_FOUND |
| gemini-3.5-flash-lite | OK | 404 |
| gemini-3.5-flash | OK | OK |
| gemini-3.6-flash | OK | 404 |
| gemini-3.7-flash | OK | 404 |
| gemini-3.8-flash | OK | 404 |

- Working location for all candidates: `global` (keep `vertex_location = global`; asia-southeast1 only serves gemini-3.5-flash).
- `thoughts_token_count`: None (not populated) for the Flash-Lite models; populated for the Flash models (3.5: 75, 3.6: 101, 3.7: 73, 3.8: 91 on a trivial prompt). Budget output tokens accordingly for Flash.
- Decision: Flash-Lite = `gemini-3.1-flash-lite` (cheapest that returned OK, global). Flash = `gemini-3.5-flash` (returned OK in global; GA-stable per the lifecycle evidence below). `backend/app/config.py`: `gemini_flash_id = "gemini-3.5-flash"`, `gemini_flash_lite_id = "gemini-3.1-flash-lite"`, `vertex_location = "global"`.
- Lifecycle evidence, fetched 2026-10-04 from https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions:
  - "Models that will be available for at least 12 months after initial release" lists: gemini-3.5-flash-lite (released 2026-07-21), gemini-3.5-flash (2026-05-19, retirement 2027-05-19 or later), gemini-3.1-flash-lite (2026-05-07, retirement 2027-05-07 or later).
  - "Models available for shorter availability periods" lists: gemini-3.8-flash (2026-09-02), gemini-3.7-flash (2026-08-13), gemini-3.6-flash (2026-07-21), all "No retirement date announced"; replacement for 3.6/3.7 is gemini-3.8-flash.
  - The page contains no "preview" label and never uses the word "GA" for these models, so GA vs preview status of 3.6/3.7/3.8-flash is **unverified**. They are not in the 12-month-commitment table, so they are NOT used (constraint: GA models only). 3.5-flash and 3.1-flash-lite are the models confirmed in the stable table.
  - Pricing page (below) labels preview models explicitly ("Gemini 3.1 Pro Preview", "Gemini 3 Flash Preview"); gemini-3.5-flash, 3.5-flash-lite and 3.1-flash-lite carry no Preview label there.
- Prices per 1M tokens, global, standard tier, input / text output (incl. reasoning), from https://docs.cloud.google.com/vertex-ai/generative-ai/pricing fetched 2026-10-04:
  - gemini-3.1-flash-lite: $0.25 / $1.50 (non-global $0.275 / $1.65)
  - gemini-3.5-flash-lite: $0.30 / $2.50 (non-global $0.33 / $2.75)
  - gemini-3.5-flash (chosen): $1.50 / $9.00 (non-global $1.65 / $9.90)
  - Non-global regions are listed at +10% on those rows (the page's own "Non-global" figures).
  - For reference only (not selected): gemini-3.6/3.7/3.8-flash show introductory $0.75 / $3.75 through 2026-12-31, then $1.50 / $7.50 from 2027-01-01 (same page, footnote text).

## B. Gemma VM rename

- VM `gemma-llm` (asia-southeast1-c, a2-ultragpu-1g, TERMINATED) renamed to `kenneth-gemma-llm` via `gcloud compute instances set-name`. Succeeded. VM was not started.
- External IP 34.126.172.79 IS a reserved static address: `gemma-llm-ip` (EXTERNAL, region asia-southeast1). No new address was created. The nip.io hostname `llm-34-126-172-79.nip.io` therefore stays valid after restart.
- Old name occurrences in instance JSON: only the instance `name`, `selfLink`, and the boot disk `source` (disk is still named `gemma-llm`; disks are not renamed). Metadata keys (auto-shutdown-minutes, hf-token, install-nvidia-driver, llm-hostname, max-model-len, model-id, startup-script, vllm-api-key) were not edited.
- Re-checked read-only (`gcloud compute addresses describe gemma-llm-ip --region asia-southeast1`, 2026-10-04): status IN_USE, addressType EXTERNAL, `users` still lists `.../instances/gemma-llm`. This is not merely transient staleness: the address's user link still points at the old instance name (the reference was not updated by `set-name`). The address remains reserved and attached to the renamed instance's NIC (instance list shows 34.126.172.79), so function is unaffected; treat the link as cosmetic and verify by starting the VM later. Address and boot disk keep the old `gemma-llm*` names.

## C. Per-persona DLS API key minting

- `scripts/spikes/derived_key.py` with the project admin key: CREATE FAILED.
  Exact error: `BadRequestError(400, 'illegal_argument_exception', 'creating derived api keys requires an explicit role descriptor that is empty (has no privileges)')`.
  Cause: `OBS_ES_ADMIN_KEY` is itself an API key, so a key created with it is a "derived" key, which may only have an empty role descriptor.
- Kibana console proxy fallback (`POST /api/console/proxy?path=/_security/api_key`) with the same key: 400 `uri [/api/console/proxy] with method [post] exists but is not available with the current configuration`.
- Result: **minting does NOT work** with the project API key. Not tried (needs a human/credentials): Kibana Dev Tools in the browser (runs as the logged-in user, which is not a derived key, so likely works; copy/paste procedure feeding `secrets/persona_keys.json`), or a user-credential-based `create_api_key`. Fallbacks: Elastic Cloud API key with a project role, or filtered aliases (weaker than DLS). USER DECISION REQUIRED before Task 4.

## D. Dataset-tagged OTel log routing (Observability project)

- OTLP endpoint (`OBS_OTLP_URL` + `/v1/logs`) accepted the project admin key (`Authorization: ApiKey ...`); no separate OTLP key needed. `Settings` needs no `obs_otlp_key`.
- Sent log attributes `data_stream.dataset=genai_guardrail`, `genai.prompt_text=p0 probe prompt`.
- Landed in data stream `logs-genai_guardrail.otel-default` (backing index `.ds-logs-genai_guardrail.otel-default-2026.10.04-000001`), template `logs-otel@template`.
- `data_stream.dataset` was honoured, with an `.otel` suffix appended: stored `data_stream: {type: logs, dataset: genai_guardrail.otel, namespace: default}`.
- Prompt text field path: `attributes.genai.prompt_text` (searchable, `exists` query matches). Log message is at `body.text`. Other top-level fields: `@timestamp, attributes, body, data_stream, observed_timestamp, resource, scope, severity_number, severity_text`.
- `logs@custom`: GET returned 404 (absent); `PUT _ingest/pipeline/logs@custom {"processors":[]}` succeeded (acknowledged). It now exists as an empty pipeline (description "p0 probe: empty custom pipeline") created by this spike.
- Top-level `security.*`: direct `POST logs-genai_guardrail.otel-default/_doc {"security":{"threat_verdict":"CLEAN"}}` was accepted and `security.threat_verdict` is retained in `_source`, BUT it is NOT indexed: the template mapping has `dynamic: false` at the root and no `security` property, and `term security.threat_verdict: CLEAN` returned 0 hits. So it is not searchable/aggregatable for ES|QL or dashboards.
- **GUARD_PREFIX for Task 7 = `attributes.security`** (the `attributes` object is mapped and searchable, as shown by `attributes.genai.prompt_text`). Alternative (not needed): map top-level `security` via a `logs-otel@custom` component template.
- `logs@custom` should be KEPT and reused by Task 7: its install_pipeline.py GETs it first and appends the hook processor rather than overwriting.
- Leftovers: two probe docs (OTLP probe; security probe) remain in the data stream.
