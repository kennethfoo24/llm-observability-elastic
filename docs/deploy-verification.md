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
