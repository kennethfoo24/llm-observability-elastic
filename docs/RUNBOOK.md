# Glass Box runbook

Live site: https://107-178-251-254.sslip.io (host built from the static IP `glassbox-ip` and the public sslip.io DNS service).
Everything runs in the namespace `genai-demo` on the GKE cluster `kenneth-gke` (project `elastic-sa`, zone `asia-southeast1-a`).
Every script checks the gcloud project and the kube context before it changes anything, and every script accepts `DRY_RUN=1` to print what it would do.

## 1. One-time setup (already done on 2026-10-05; repeat only for a fresh project)

Run in this order from the repo root:

1. `deploy/scripts/gcp_bootstrap.sh`: Artifact Registry repo `glassbox`, static IP `glassbox-ip`. No service accounts: the LLM is the Elastic Inference Service, reached with the guardrail API key. Prints the host name.
2. Image build: GitHub Actions (`.github/workflows/build-image.yml`) runs the backend and frontend tests, then pushes `docker.io/kennethfoo24/glassbox:<git sha>` (linux/amd64) on every push to `main` or `feat/glassbox-deploy` that touches the app. The run summary prints the digest; deploy with `IMAGE=docker.io/kennethfoo24/glassbox@<digest>`. Repo secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`. `deploy/scripts/build_push.sh` (Cloud Build to Artifact Registry) remains as a fallback.
3. Mint the persona keys with `docs/dev-tools-mint-keys.md` (Kibana Dev Tools), save them to `backend/secrets/persona_keys.json`. Optional hardening: ingest-only log keys from `docs/dev-tools-mint-ingest-keys.md`.
4. `deploy/scripts/create_secrets.sh`: writes the Kubernetes Secrets from local gitignored files and prints key names only. It creates the demo password in `backend/secrets/app_password.txt` the first time. Today it runs with `ALLOW_ADMIN_LOG_KEYS=1` (see section 5).
5. `IMAGE=<image@digest> WITH_TRAFFICGEN=1 deploy/scripts/deploy.sh`: applies the manifests, waits for the rollout and the managed certificate (up to 90 minutes), then checks `https://<host>/healthz`. It only says "ok" after healthz returns 200.
6. Elastic content (dashboards, cost alert, guardrail pipeline, detection rule): `python -m elastic.apply --project observability` and `--project security`, and `PROJECT=<observability|security> bash scripts/import_models.sh` and `python scripts/install_pipeline.py --project <name>` once per project (see `docs/deploy-verification.md`, Task 6).

## 2. Before a demo

```
deploy/scripts/demo_up.sh            # app at 1 replica, traffic generator un-suspended, waits for /healthz
deploy/scripts/demo_up.sh --gemma    # also starts the Gemma VM and waits for it (5 to 10 minutes, about $5 to $6 per hour)
```

The script prints the URL and reminds you that the password is in `backend/secrets/app_password.txt`. It never prints the password. Open the file yourself to read it.
Start Gemma at least 10 minutes before you need it. It switches itself off 180 minutes after boot.

## 3. During the demo: where to look

| What | Where |
|---|---|
| Traces | Kibana, Observability, APM, service `glassbox-backend` (the app has an "Open trace in Kibana" link too) |
| Glass Box dashboard | Kibana, Dashboards, `Glass Box: LLM observability` (cost, tokens, guardrail verdicts, stage latency) |
| LLM provider usage | Elastic Cloud, Billing and subscription, Usage, Inference (EIS token usage per model). APM GenAI service views and the Kubernetes infrastructure dashboards cover the rest of pillar 1 |
| Security alerts | Kibana, Security project, Alerts, rule `glassbox-flagged-prompts` |
| Cost alert | Observability, Rules, `Glass Box: LLM spend above threshold` (threshold 0.25 USD per hour) |

## 4. After a demo

```
deploy/scripts/demo_down.sh              # suspends the traffic generator, stops Gemma, confirms both
deploy/scripts/demo_down.sh --teardown   # also removes the Ingress and load balancer and scales the app to 0
```

`demo_down.sh` fails loudly if the CronJob is not suspended or the Gemma VM is not TERMINATED. After `--teardown`, bring the site back with `IMAGE=<image@digest> deploy/scripts/deploy.sh` (the certificate wait applies again; get the full image reference of what is running with `kubectl -n genai-demo get deploy glassbox -o jsonpath='{.spec.template.spec.containers[0].image}'`, or use the digest from the latest GitHub Actions run for a new build) and then `demo_up.sh`. `teardown.sh --all` additionally deletes the namespace after you type `delete genai-demo`; it is rarely needed.
Leave the CronJob suspended between demos. The traffic generator is the only part that spends money on its own.

## 5. Key lifecycle

| Key | Facts | What to do |
|---|---|---|
| Persona keys (employee, manager, catalog, guardrail; any extra hr or exec keys in the file are unused and harmless) | Minted 2026-10-05 with a 90 day expiry, so they expire on 2027-01-03 | Before that date: re-mint with `docs/dev-tools-mint-keys.md`, save to `backend/secrets/persona_keys.json`, run `deploy/scripts/create_secrets.sh`, then `kubectl -n genai-demo rollout restart deployment/glassbox`. An expired key makes every chat fail with 502 |
| Demo password | Rotated once after it appeared in a tool output during the first smoke run. The old password is invalid | Replace the contents of `backend/secrets/app_password.txt`, run `create_secrets.sh`, restart the deployment |
| Guardrail log export keys | By the project owner's decision these are the project admin keys (`ALLOW_ADMIN_LOG_KEYS=1`). A compromised pod would expose admin access to both projects | Open item: replace with ingest-only keys from `docs/dev-tools-mint-ingest-keys.md`, then re-run `create_secrets.sh` without the override and restart |
| Plaintext OTLP key on `o11y-metrics/chatbot-rag-app` | Intentionally untouched, by the project owner's decision. Only note: its value appeared in this project's working notes | No action here |
| Gemma API key | Read from the VM metadata into memory when needed, never stored in git | None |

## 6. Known behaviours (not faults)

- EIS token usage under Billing and subscription lags behind real traffic, so an empty Inference usage chart right after a demo is expected.
- On first deploy the managed certificate can take up to about 60 minutes to become Active. Until then HTTPS fails and HTTP redirects to it.
- The first chat after a long idle period is slower because the ML models scale down after 24 hours without use.
- Gemma first boot took 511 seconds in the measured run (a first boot after a long stop). A warm restart was not measured. Plan for 5 to 10 minutes. The Local SSD is kept on stop by default; a stopped VM may still incur Local SSD storage charges, see the cost table for how to check and for `GEMMA_DISCARD_SSD=1`.
- The browser waits at most 90 seconds for an answer. The load balancer allows 100 seconds, the server stays below the browser limit.
- Rate limits are per IP: 20 chats per minute and 120 API requests per minute. About 10 failed attempts in 5 minutes (each wrong password counts once) lock that IP out for wrong or missing passwords. Requests with the correct password bypass the lockout, because the lockout only exists to throttle guessing.
- Traces show up about 1 minute after a request.
- The Gemma VM exposes vLLM `/metrics` without a password. This is an accepted risk (counters only, no prompts) until the gated proposal is approved: `basic_auth` on `/metrics`, a Prometheus integration (needs an Elastic Agent, which this deploy no longer runs) and a Gemma dashboard.

## 7. Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| Chat returns 502 `upstream_error` | `kubectl -n genai-demo logs deploy/glassbox --tail=50` for 401 or 403 from Elasticsearch | Persona keys missing or expired: re-mint and restart (section 5). If the log shows 403 from `_inference`, the guardrail key lacks inference privileges: re-mint it with `docs/dev-tools-mint-keys.md` |
| Chat returns 503 `gemma_offline` | `deploy/scripts/gemma.sh status` | Start it with `demo_up.sh --gemma`, or use "Try with GPT-5.4 mini" in the app |
| Dashboards are empty | Is the time range right? Did traffic run in the last hour? Spans take about a minute to appear | Un-suspend the generator or send chats by hand |
| No Security alerts | Security project, rule `glassbox-flagged-prompts` enabled? `logs-genai_guardrail*` receiving documents there? | Re-run `python -m elastic.apply --project security`. Confirm the Security guardrail models are started. Wait for the rule interval |
| Certificate stuck in Provisioning | `kubectl -n genai-demo get managedcertificate glassbox-cert` | Check the Ingress has the static IP annotation and DNS for the host resolves to `107.178.251.254`. Wait up to 60 minutes. Do not delete and re-create repeatedly |
| Pods in CrashLoop | `kubectl -n genai-demo describe pod -l app=glassbox` and logs | Missing or expired persona keys Secret, or a Secret key that `create_secrets.sh` did not write. Re-run `create_secrets.sh` and restart |
| Site does not answer after `--teardown` | `kubectl -n genai-demo get ingress` | Run `deploy/scripts/deploy.sh` again and wait for the certificate |

## 8. Cost and off switches

| Item | Cost | Off switch |
|---|---|---|
| HTTPS load balancer (while the Ingress exists) | about $18 per month | `demo_down.sh --teardown` |
| Traffic generator (every 5 minutes, 07:00 to 22:00 SGT) | about $0.0005 to $0.002 per request on the EIS mix (re-measure after the EIS deploy) | `demo_down.sh` (suspend) |
| LLM calls (EIS, per million tokens, billed by Elastic) | GPT-5.4 mini is the default and cheapest; see `backend/prices.yaml` for the assumed rates | `demo_down.sh` (suspend the generator) |
| Gemma VM (A100) | about $5 to $6 per hour while running, about $2 for the 23 minute test. A stopped VM that keeps its Local SSD may still incur Local SSD storage charges (a Preview feature) | `demo_down.sh`, auto stop after 180 minutes. Check charges in Cloud Billing, filtering SKUs on Compute Engine for project `elastic-sa`, or run `gcloud compute instances describe kenneth-gemma-llm --zone=asia-southeast1-c --format='value(disks)'` to see the Local SSD. `GEMMA_DISCARD_SSD=1 deploy/scripts/gemma.sh stop` discards the SSD to avoid that charge, at the price of a slower next boot and loss of its data. Default is to keep it |
| Pods, Elastic ingest | negligible | `teardown.sh` scales the app to 0 |
| Static IP `glassbox-ip` | free while attached to the load balancer; about $7 per month once unattached (after `--teardown`) | release with `gcloud compute addresses delete glassbox-ip --global --project=elastic-sa` only if you will not redeploy (a new IP changes the host name) |

Safety net: the traffic generator has `concurrencyPolicy: Forbid`, a run deadline, a hard cap of 5 requests per run, and the cost alert fires above 0.25 USD per hour.
Current state at the time of writing: the CronJob is suspended and the Gemma VM is stopped, but these still run and cost money:

- the Ingress and load balancer (about $18 per month),
- the `glassbox` app pod (no extra node cost),

`demo_down.sh` suspends the generator and stops Gemma only; it leaves the app and the load balancer up. `demo_down.sh --teardown` also removes the Ingress and load balancer and scales the app to 0, so nothing but the static IP remains.

## 9. Open items

1. Unused live objects from the Vertex era. Delete them once the EIS version is deployed (this repo no longer creates or uses them):
   - GCP: service account `glassbox-app` (its `roles/aiplatform.user` project binding and the Workload Identity binding to `genai-demo/glassbox`);
   - GCP: service account `glassbox-monitoring` (its `roles/monitoring.viewer` binding and the Workload Identity binding to `genai-demo/glassbox-monitoring`);
   - Kubernetes: Deployment `glassbox-elastic-agent`, Secret `glassbox-fleet` and ServiceAccount `glassbox-monitoring` in `genai-demo`;
   - Elastic Fleet: agent policy `glassbox-gcp` and package policy `glassbox-vertexai`, plus the unused `[GCP VertexAI]` dashboards.
2. Lens rendering of the Glass Box dashboard and the Kibana trace link were checked through REST only. Please eyeball both once in a logged-in browser.
3. Post-login UI visuals were checked by API calls and frontend tests only.
4. Guardrail log export uses project admin keys (see section 5).
5. Gemma `/metrics` is open (accepted risk) and the hardening proposal awaits approval.
6. Decision for the project owner: keep the Gemma Local SSD on stop (fast boot, possible Local SSD storage charge) or set `GEMMA_DISCARD_SSD=1` (no charge, slower next boot, data lost). Check the actual charge in billing first.

## LLM Observability deep links config

The LLM Observability links use `OBS_KIBANA_URL` (trace, Discover, cost dashboard) and `SEC_KIBANA_URL` (Security alerts link). Both come from Secret `glassbox-app` (keys `kibana_url`, `sec_kibana_url`), which `deploy/scripts/create_secrets.sh` fills from `OBSERVABILITY_KIBANA` and `SECURITY_KIBANA` in `elasticsearch.txt`. Re-run it before deploying this version. If `sec_kibana_url` is empty the Security links are hidden. The Discover and alerts URL states use Kibana rison format; open each once in a logged-in browser.
