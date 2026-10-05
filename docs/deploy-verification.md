# First GKE deployment and live smoke (2026-10-05)

Host: `https://107-178-251-254.sslip.io` (static IP `107.178.251.254`, Ingress `glassbox` in `genai-demo`, managed certificate Active about 25 minutes after apply).
Image: `asia-southeast1-docker.pkg.dev/elastic-sa/glassbox/app@sha256:6a3665fc...` (Cloud Build, linux/amd64).
Guardrail log export uses the project admin keys by the user's decision (`ALLOW_ADMIN_LOG_KEYS=1`).

## Smoke results

| Item | Result | Evidence (no secrets) |
|---|---|---|
| a. Auth | PASS (lockout skipped) | Unauthenticated `/api/personas` returns 401. The 11-wrong-password lockout was not run live (unit tests cover it; avoids locking out the user's IP). |
| b. Real DLS | PASS | Maya: `hidden` includes `project-aurora`, answer says the documents do not contain it. Rachel: answer cites `[project-aurora]`, `hidden` empty. |
| c. Red team | PASS | Injection: `blocked=true`, reason `prompt_injection`. Email: `blocked=true`, `pii_email`. Salary: flagged `pii_salary` and answered. Two colleagues: flagged `pii_multiple_people` (NER model). |
| d. Traces | PASS (API only) | Elasticsearch REST: service `glassbox-backend`, resource `k8s.pod.name` set, spans `guardrail.check`, `retrieval.hybrid`, `prompt.build`, `generate_content gemini-*` with `gen_ai.input.messages`/`output.messages`, `app.genai.cost_usd` on the root span. Guardrail logs arrived in both projects (8 and 8 for 8 requests). Trace link pattern `{kibana}/app/apm/link-to/trace/{trace_id}` is well-formed. Opening it in Kibana was not done (SSO, no browser session). Traces appear about 1 minute after the request. |
| e. LangChain | PASS | Stages: `guardrail.check`, `retrieval.hybrid`, `llm.generate` (three). SDK engine shows four (adds `prompt.build`). |
| f. Models | PASS | `/api/models`: Gemma `available=false` (VM stopped, UI shows Offline); Flash-Lite and Flash answered. Gemini citation format seen: `[doc-id]` only (for example `[pto-policy]`, `[salary-bands]`); no lists or other syntaxes. |
| g. Headers/CSP | PASS | `content-security-policy` (default-src self, frame-ancestors none), `strict-transport-security: max-age=31536000`, `x-content-type-options`, `referrer-policy: no-referrer`. HTTP redirects 301 to HTTPS. No CSP violation on the login page. |

Other checks: Workload Identity (`google.auth.default()` project `elastic-sa`), pod logs contain no key material, `automount` token off.

Not covered live: post-login browser visuals (X-ray drawer, chips) because typing the password in the browser tool would expose it; the same behaviour is covered by the API checks above and the frontend tests.

## Polish items
- `/favicon.ico` returns 404 (console noise, harmless).
- Maya's Aurora answer and the "two colleagues" answer carry no citation (the model correctly said the documents do not cover it).

## Notes
- The demo password was exposed once in tool output during the smoke run and was rotated (file regenerated, Secret re-applied, deployment restarted); the old one now returns 401.
- Build fix found on first deploy: Cloud Build needs `DOCKER_BUILDKIT=1` for `COPY --chmod`.

## Left running (cost)
Ingress and load balancer (about $18 per month), one `glassbox` pod. No CronJob, Gemma VM stopped.

## Task 6: live telemetry, guardrail, dashboard and alert proofs (2026-10-05)

All checks via Elasticsearch and Kibana REST (Kibana is SSO only, no logged-in browser). Lens rendering of the dashboard is NOT confirmed visually; each panel's ES|QL was run through `POST /_query` instead.

| Step | Result |
|---|---|
| 1a Traces | 5 chats: service `glassbox-backend`, `k8s.pod.name` set, spans `guardrail.check`, `retrieval.hybrid`, `prompt.build`, `generate_content gemini-3.1-flash-lite`, `POST /api/chat` present within about 1 minute. |
| 1b Guardrail logs | 5 prompts (3 benign, 1 injection, 1 email): 5 new docs in `logs-genai_guardrail*` in Observability and 5 in Security. Observability verdicts: CLEAN x3, FLAGGED (`prompt_injection`) and FLAGGED (`pii_email`). Shared `logs.otel`: 0 documents for service `glassbox-backend` and 0 containing the prompt markers (no leak). |
| 2 Security models | `PROJECT=security bash scripts/import_models.sh` (target confirmed as the Security host first): both models `started` with adaptive allocations 1..2; `_infer` works for both. `install_pipeline.py --project security` installed `genai-guardrail` and the `logs@custom` hook (existing processors kept). Live Security verdicts: benign CLEAN, injection FLAGGED, email FLAGGED, `models_ok=true` (before the install: `models_ok=false`, injection UNKNOWN). |
| 3a Dashboard `glassbox-overview` | Saved object GET 200, 8 panels. ES|QL per panel (last 24 h), rows: spend over time by model 3, avg cost per persona 3, total spend 1 (about 0.006 USD), tokens by model 2, requests by engine 2, guardrail verdicts 2, guardrail logs over time 6, p95 latency by stage 4. No panel errored or empty. |
| 3b Cost rule `glassbox-llm-spend` | Enabled, interval 1m. With `--cost-threshold 0.0001` and two chats an alert (`kibana.alert.status` active) appeared in the `.alerts-*` index within 20 s, `last_run.outcome` succeeded, `execution_status` active. Threshold restored with `--cost-threshold 0.25` and verified by GET (query ends `WHERE spend > 0.25`). The proof alert may stay active until the rule next recovers. |
| 3c Security rule `glassbox-flagged-prompts` | Enabled, last execution succeeded. After the injection and email prompts, `POST /api/detection_engine/signals/search` returned 4 signals with `kibana.alert.rule.rule_id` `glassbox-flagged-prompts` in the last 30 minutes (alert_suppression payload accepted). |
| 4 Resilience | `kubectl set env` with the three endpoints at `http://127.0.0.1:9` (names match `backend/app/config.py` and the manifest): rollout completed, pod Ready (1/1, 0 restarts), 3 chats returned HTTP 200 in 2.3 s, 0.2 s and 1.3 s (one was an injection prompt). Restore: re-applying the rendered `30-app.yaml` failed once with `valueFrom may not be specified when value is not empty` because `set env` replaced the two secret-backed endpoint vars with literals; fix: `kubectl set env ... GUARDRAIL_LOG_OBS_ENDPOINT- GUARDRAIL_LOG_SEC_ENDPOINT-` then re-apply (Secret refs and the collector endpoint confirmed restored). After restore: 2 new `POST /api/chat` traces and 2 new guardrail log docs in each project. |

## Task 7: Vertex AI Fleet integration (2026-10-05) - BLOCKED on credentials

- Installed `gcp_vertexai` 1.5.0 in the Observability project; agent policy `glassbox-gcp`, package policy `glassbox-vertexai` (only `gcp_vertexai.metrics` enabled; audit-log and BigQuery streams disabled), `project_id=elastic-sa`, no credential vars.
- Dashboards installed by the package: `[GCP VertexAI] Metrics Overview`, `[GCP VertexAI] AuditLogs` (the `search=Vertex` find returns none because the saved-object search is title-prefix based; found via the package's installed_kibana assets). Rendering not viewed (no browser session, SSO).
- Agent: Deployment `glassbox-elastic-agent` (`elastic-agent:9.5.0`, non-root uid 1000, caps dropped, no privileged/hostPath/hostNetwork, writable emptyDir only for `/usr/share/elastic-agent/state`, KSA `glassbox-monitoring`). Enrolled and Fleet status `online` within about 90 s (a 9.5.0 agent is accepted by the 9.6.0 stack).
- ADC via Workload Identity does NOT work for this input: component `gcp/metrics-default` goes STARTING -> FAILED with `Permanent: no credentials_file_path or credentials_json specified`. No metrics data stream (`metrics-gcp*`) was created (0 docs) after 15+ minutes and 11 successful chats on Flash-Lite and Flash. No key was created.
- Workload Identity itself is bound (`roles/iam.workloadIdentityUser` for `genai-demo/glassbox-monitoring`).

## Task 8: traffic generator rollout and cost watch (2026-10-05)

- Applied `50-trafficgen.yaml` rendered with the running image; it stayed `suspend: true`. Manual job `manual-1`: Complete in 20 s, one JSON line, `status 200`, verdict CLEAN, no prompt text; job deleted.
- Un-suspended at 20:29 SGT (inside the `*/5 7-21` window) and observed until 21:31 SGT: 13 scheduled jobs (20:30 to 21:30), all Complete, never more than one at a time (`concurrencyPolicy: Forbid`); history kept to the last 2 successful jobs (`successfulJobsHistoryLimit: 2`).
- ES|QL (`traces-generic.otel-default`, `service.name == "glassbox-backend"`, since 20:29 SGT): 13 requests, 12 CLEAN and 1 FLAGGED/blocked ($0). Flash-Lite 11 billed, avg $0.000185; Flash 1 at $0.00539; total $0.0074; avg $0.00057 per request. Guardrail logs (`logs-genai_guardrail*`) for the window: 13 docs, `attributes.security.threat_verdict` CLEAN 12, FLAGGED 1 (the 15% attack mix gave 1 flagged of 13, expected about 2).
- Cost rule `glassbox-llm-spend`: `execution_status` ok, threshold still `spend > 0.25`, 0 active alerts (the Task 6 proof alert is not active).
- Off switch: `suspend` patched true at 21:31:47 SGT; no job started at the 21:35 boundary (lastScheduleTime stayed 13:30Z). Leftover jobs deleted. Final state: CronJob SUSPENDED (un-suspend for demos).

## Task 9: Gemma VM operations and live measurements (2026-10-05)

`deploy/scripts/gemma.sh start|stop|status|wait` (zone `asia-southeast1-c`, project guard, `DRY_RUN=1` echoes start/stop/wait; `wait` polls `/v1/models` every 15 s up to 15 minutes, Bearer key read from VM metadata into memory and passed to curl through stdin config, never printed). `stop` must pass `--discard-local-ssd=false` (the VM has a Local SSD; plain `stop` fails with HTTP 400, found live, fixed in the script).

| Item | Result |
|---|---|
| VM timeline (UTC) | start requested 13:39:24, `wait` first 200 at 13:47:55, stop completed 14:02:26, status TERMINATED. Total uptime about 23 minutes (about $2 at $5-6/h). |
| Cold start | 511 s from `start` to first HTTP 200 on `/v1/models` (18 s for the API call, then 492 s of `wait`: 502 from Caddy while vLLM loaded the model). This WAS a first boot after a long stop (last stop 2026-07-20, last start 2026-07-19), so the figure includes whatever the boot installs; a warm restart was not measured. |
| Availability flip | `/api/models` showed `gemma available=true` on the first request after `wait` returned 200 (about 6 s later, inside the 15 s gate TTL). |
| 5 chats on Gemma (via the deployed app, password header) | All HTTP 200, none blocked. personas/engines: employee/sdk, manager/langchain, hr/sdk, exec/langchain, employee/sdk. Wall time 4.29, 1.33, 1.33, 3.44, 3.98 s. Answer lengths 147, 86, 77, 282, 287 characters. `llm.generate` stage (ms): 3763, 909, 864, 3048, 3656. Guardrail 112-212 ms, retrieval 159-250 ms. Reported cost (amortised assumption) 0.0021-0.0027 USD per chat. |
| LLM span durations (ES, `traces-*`, read-only, matched by trace id) | span `chat google/gemma-4-31B-it`: 3.66 s, 0.73 s (+0.73 s LangChain duplicate), 0.86 s, 3.04 s (+3.04 s LangChain duplicate), 3.66 s. They match the `llm.generate` stage within about 100 ms. LangChain chats also carry an `invoke_workflow RunnableSequence` span (0.74 s, 3.05 s). |
| vLLM `/metrics` | GET without credentials returns 200 (open to the internet). Before chats: prompt 0, generation 0. After the 5 chats (21:49:39 SGT): `vllm:prompt_tokens_total` 2141, `vllm:generation_tokens_total` 226. Ten minutes later (22:00:19 SGT, window 10.7 min, no traffic sent): both unchanged, so the counters are correct and the idle rate is 0. Demo-load throughput is therefore not a steady-state number: 5 chats = 2141 prompt + 226 generated tokens (about 428 prompt and 45 generated tokens per chat). |
| `backend/prices.yaml` | NOT changed. The `assumed_tokens_per_hour` amortisation assumption stands; whether to base it on a measured steady throughput is a user decision (a real load test would be needed; demo traffic is not a steady rate). |
| Offline (after stop) | `/api/models` showed `gemma available=false` on the first poll after the VM reached TERMINATED (8 s cadence, 3 samples, all false). `POST /api/chat` model `gemma` returned HTTP 503 `{"error":"gemma_offline","hint":"Gemma VM is not serving; ..."}` in 0.06 s; `/api/health/gemma` answered 200. The same message on model `flash-lite` returned 200, so the retry-on-Flash-Lite path works API side (the inline error and the "Try with Gemini Flash-Lite" button are UI-covered by frontend tests). |
| Traffic generator | CronJob `glassbox-trafficgen` has `GEMMA_TRAFFIC=0` (unset would also mean off) and is currently suspended. |

Accepted risk (Step 4 NOT done, needs the user's yes): the VM's Caddy exposes vLLM `/metrics` without authentication on `https://llm-34-126-172-79.nip.io/metrics` (counters, queue sizes, model name; no prompts). Proposal for the user: `basic_auth` on `/metrics` in the VM startup-script Caddyfile plus a Prometheus integration on the `glassbox-gcp` agent and a "Gemma (vLLM)" dashboard. Until approved it stays open and is recorded here as an accepted risk. The VM's `/v1/*` paths remain behind the Bearer key.

## Task 10: demo scripts, runbook and final record (2026-10-05)

`deploy/scripts/demo_up.sh [--gemma]` and `demo_down.sh [--teardown]` use only commands proven in Tasks 5-9 (scale, CronJob patch, `gemma.sh`, `teardown.sh`). Dry-run tests are in `deploy/tests/test_scripts.py`.
Live run (not `--gemma`, not `--teardown`): `demo_down.sh` confirmed "cronjob suspended" and Gemma TERMINATED; `demo_up.sh` scaled the app to 1 (rollout ok), un-suspended the CronJob and `https://107-178-251-254.sslip.io/healthz` answered 200. `demo_down.sh` was then run again so the CronJob is left suspended (cost control); final state is recorded in the task report. `demo_up.sh --gemma` was dry-run only (Gemma was not started in this task).

Final suites: backend `pytest -q`: 189 passed (22 integration deselected). `pytest elastic/tests deploy/tests -m "not integration"`: 55 passed (10 deselected); this run includes the uncommitted work-in-progress `elastic/tests/test_fleet.py`. Frontend `npm test`: 229 passed (25 files).

## Final checklist

### Review Focus (plan)

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Certificate wait, no success before healthz 200 | PASS | `deploy.sh` waits up to 90 minutes and then curls healthz; live: certificate Active about 25 minutes after apply, healthz 200 (Task 5, Task 10 live up) |
| 2 | Slow answers not cut by the LB | PASS (config) | BackendConfig `timeoutSec: 100`, server upstream timeouts below 90 s; Gemma chats up to 4.3 s live. No deliberately slow 60 s request was run |
| 3 | Secrets never in git, logs, describe, argv | PASS | No key in pod logs (Task 5); scripts read local files and print names only; scan tests in `deploy/tests`; persona key expiry 2027-01-03 documented in the runbook. One password exposure happened and was rotated (see Notes above) |
| 4 | Traffic generator cost guard | PASS | `concurrencyPolicy: Forbid`, deadline, cap of 5 per run, suspend switch verified at 21:35, 13 scheduled jobs never overlapped, cost rule `ok` (Task 8) |
| 5 | App keeps answering when telemetry endpoints are dead | PASS | 3 chats HTTP 200 with dead endpoints, pod Ready 0 restarts (Task 6) |
| 6 | Guardrail logs reach both projects, same verdict, no `logs.otel` leak | PASS | 5 and 5 docs, verdicts match, 0 leaked docs in `logs.otel` (Task 6) |
| 7 | Vertex metrics lag documented | PASS (docs) | Runbook section 6. The lag itself could not be measured because Vertex collection is blocked (open item 1) |

### Carried live-smoke list

| Item | Result | Evidence |
|---|---|---|
| a Auth (401, lockout) | PASS, lockout not run live | Unit tests cover lockout |
| b Real DLS Maya vs Rachel | PASS | Task 5 section b |
| c Red team (injection, email, salary, two names) | PASS | Task 5 section c |
| d Traces with content capture | PASS via REST; Kibana trace link not opened | No SSO browser session |
| e LangChain stages | PASS | Task 5 section e |
| f Models and Gemma Offline | PASS | Task 5 section f, Task 9 |
| g Headers, CSP, redirect | PASS | Task 5 section g |
| Dashboard `glassbox-overview` | PASS via ES|QL per panel; Lens rendering NOT VERIFIED | Task 6 3a |
| Cost alert fires, threshold restored | PASS | Task 6 3b |
| Security detection rule fires | PASS | Task 6 3c |
| Traffic generator schedule and off switch | PASS | Task 8 |
| Gemma start, chats, stop | PASS | Task 9 (cold start 511 s) |
| Vertex AI integration data | NOT VERIFIED (blocked) | Task 7: agent online, `gcp/metrics` failed, no data |
| Post-login browser visuals | NOT VERIFIED visually | API and frontend tests only |
| demo_up and demo_down live | PASS | Task 10 live run above |

## Open items

1. Vertex AI integration incomplete: `gcp_vertexai` needs `credentials_json`. The project owner chose a service-account key for `glassbox-monitoring`; key creation was denied by the permission system and not done. `elastic/fleet.py` and `elastic/tests/test_fleet.py` hold uncommitted `credentials_json` support. Finishing commands are in `docs/RUNBOOK.md` section 9.
2. Please eyeball once: the Glass Box dashboard (Lens rendering) and the Kibana trace link (verified through REST only).
3. Post-login UI visuals verified by API and frontend tests only.
4. Guardrail log export uses project admin keys (owner decision), not ingest-only keys. `docs/dev-tools-mint-ingest-keys.md` exists for later hardening.
5. Gemma vLLM `/metrics` is open (accepted risk); the gated proposal (basic_auth, Prometheus integration, Gemma dashboard) awaits approval. Gemma warm restart time and whether to base `assumed_tokens_per_hour` on measured throughput are undecided.
6. The plaintext OTLP key on `o11y-metrics/chatbot-rag-app` is untouched by decision; its value appeared in this project's working notes.
7. Persona keys expire 2027-01-03 (minted 2026-10-05).
8. Parked minors: IPv6 /64 limiter weakness, per-replica limiter state, `/favicon.ico` 404, Task 7 and Task 3 minors in the ledger.
