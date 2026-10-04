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
- Decision: Flash-Lite = `gemini-3.1-flash-lite` (cheapest, global). Flash = `gemini-3.8-flash` (newest returning OK, global). `backend/app/config.py` `gemini_flash_id` set to `gemini-3.8-flash`; `gemini_flash_lite_id` stays `gemini-3.1-flash-lite`.
- Prices per 1M tokens, Vertex pricing page (global, standard, input / text output incl. reasoning):
  - gemini-3.1-flash-lite: $0.25 / $1.50
  - gemini-3.5-flash-lite: $0.30 / $2.50
  - gemini-3.5-flash: $1.50 / $9.00
  - gemini-3.8-flash (also 3.6 / 3.7): introductory $0.75 / $3.75 through 2026-12-31, then $1.50 / $7.50 from 2027-01-01. Non-global regions cost +10%.
- Not verified: whether the page marks each model GA vs preview. The calls succeeded without any preview opt-in, but GA status was not confirmed. Fallback if 3.8 is preview: `gemini-3.5-flash`.

## B. Gemma VM rename

- VM `gemma-llm` (asia-southeast1-c, a2-ultragpu-1g, TERMINATED) renamed to `kenneth-gemma-llm` via `gcloud compute instances set-name`. Succeeded. VM was not started.
- External IP 34.126.172.79 IS a reserved static address: `gemma-llm-ip` (EXTERNAL, region asia-southeast1). No new address was created. The nip.io hostname `llm-34-126-172-79.nip.io` therefore stays valid after restart.
- Old name occurrences in instance JSON: only the instance `name`, `selfLink`, and the boot disk `source` (disk is still named `gemma-llm`; disks are not renamed). Metadata keys (auto-shutdown-minutes, hf-token, install-nvidia-driver, llm-hostname, max-model-len, model-id, startup-script, vllm-api-key) were not edited.
- Cosmetic: the address `gemma-llm-ip` "users" link still showed the old instance URL immediately after rename (likely stale for a moment). Address and boot disk keep the old `gemma-llm*` names.

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
- Leftovers: two probe docs (OTLP probe; security probe) remain in the data stream.
