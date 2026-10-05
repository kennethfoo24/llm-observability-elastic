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
