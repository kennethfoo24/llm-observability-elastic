# Glass Box runbook

Live site: https://107-178-251-254.sslip.io (host built from the static IP `glassbox-ip` and the public sslip.io DNS service).
Everything runs in the namespace `genai-demo` on the GKE cluster `kenneth-gke` (project `elastic-sa`, zone `asia-southeast1-a`).
Every script checks the gcloud project and the kube context before it changes anything, and every script accepts `DRY_RUN=1` to print what it would do.

## 1. One-time setup (already done on 2026-10-05; repeat only for a fresh project)

Run in this order from the repo root:

1. `deploy/scripts/gcp_bootstrap.sh`: Artifact Registry repo `glassbox`, static IP `glassbox-ip`, service accounts `glassbox-app` (Vertex AI user) and `glassbox-monitoring` (monitoring viewer), Workload Identity bindings. Prints the host name.
2. `deploy/scripts/build_push.sh`: Cloud Build image for linux/amd64. Prints `image@digest`.
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
| Vertex AI dashboards | `[GCP VertexAI] Metrics Overview` and `[GCP VertexAI] AuditLogs`. Available once Vertex credentials are in place (see section 9, open item 1). Until then they exist but have no data |
| Security alerts | Kibana, Security project, Alerts, rule `glassbox-flagged-prompts` |
| Cost alert | Observability, Rules, `Glass Box: LLM spend above threshold` (threshold 0.25 USD per hour) |

## 4. After a demo

```
deploy/scripts/demo_down.sh              # suspends the traffic generator, stops Gemma, confirms both
deploy/scripts/demo_down.sh --teardown   # also removes the Ingress and load balancer and scales the app to 0
```

`demo_down.sh` fails loudly if the CronJob is not suspended or the Gemma VM is not TERMINATED. After `--teardown`, bring the site back with `IMAGE=<image@digest> deploy/scripts/deploy.sh` (the certificate wait applies again) and then `demo_up.sh`. `teardown.sh --all` additionally deletes the namespace after you type `delete genai-demo`; it is rarely needed.
Leave the CronJob suspended between demos. The traffic generator is the only part that spends money on its own.

## 5. Key lifecycle

| Key | Facts | What to do |
|---|---|---|
| Persona keys (employee, manager, hr, exec, catalog, guardrail) | Minted 2026-10-05 with a 90 day expiry, so they expire on 2027-01-03 | Before that date: re-mint with `docs/dev-tools-mint-keys.md`, save to `backend/secrets/persona_keys.json`, run `deploy/scripts/create_secrets.sh`, then `kubectl -n genai-demo rollout restart deployment/glassbox`. An expired key makes every chat fail with 502 |
| Demo password | Rotated once after it appeared in a tool output during the first smoke run. The old password is invalid | Replace the contents of `backend/secrets/app_password.txt`, run `create_secrets.sh`, restart the deployment |
| Guardrail log export keys | By the project owner's decision these are the project admin keys (`ALLOW_ADMIN_LOG_KEYS=1`). A compromised pod would expose admin access to both projects | Open item: replace with ingest-only keys from `docs/dev-tools-mint-ingest-keys.md`, then re-run `create_secrets.sh` without the override and restart |
| Plaintext OTLP key on `o11y-metrics/chatbot-rag-app` | Intentionally untouched, by the project owner's decision. Only note: its value appeared in this project's working notes | No action here |
| Gemma API key | Read from the VM metadata into memory when needed, never stored in git | None |

## 6. Known behaviours (not faults)

- Vertex AI metrics lag 3 to 6 minutes, so a dashboard that is empty right after traffic is expected.
- On first deploy the managed certificate can take up to about 60 minutes to become Active. Until then HTTPS fails and HTTP redirects to it.
- The first chat after a long idle period is slower because the ML models scale down after 24 hours without use.
- Gemma first boot took 511 seconds in the measured run (a first boot after a long stop). A warm restart was not measured. Plan for 5 to 10 minutes.
- The browser waits at most 90 seconds for an answer. The load balancer allows 100 seconds, the server stays below the browser limit.
- Rate limits: 20 chats per minute per IP, 120 requests per minute overall. 10 wrong passwords in 5 minutes lock that IP out for a while.
- Traces show up about 1 minute after a request.
- The Gemma VM exposes vLLM `/metrics` without a password. This is an accepted risk (counters only, no prompts) until the gated proposal is approved: `basic_auth` on `/metrics`, a Prometheus integration on the `glassbox-gcp` agent and a Gemma dashboard.

## 7. Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| Chat returns 502 `upstream_error` | `kubectl -n genai-demo logs deploy/glassbox --tail=50` for 401 or 403 from Elasticsearch | Persona keys missing or expired: re-mint and restart (section 5). If the log shows a Vertex error, check the `glassbox-app` service account binding |
| Chat returns 503 `gemma_offline` | `deploy/scripts/gemma.sh status` | Start it with `demo_up.sh --gemma`, or use "Try with Gemini Flash-Lite" in the app |
| Dashboards are empty | Is the time range right? Did traffic run in the last hour? Vertex panels need 3 to 6 minutes and credentials | Un-suspend the generator or send chats by hand. For Vertex see section 9 |
| No Security alerts | Security project, rule `glassbox-flagged-prompts` enabled? `logs-genai_guardrail*` receiving documents there? | Re-run `python -m elastic.apply --project security`. Confirm the Security guardrail models are started. Wait for the rule interval |
| Certificate stuck in Provisioning | `kubectl -n genai-demo get managedcertificate glassbox-cert` | Check the Ingress has the static IP annotation and DNS for the host resolves to `107.178.251.254`. Wait up to 60 minutes. Do not delete and re-create repeatedly |
| Pods in CrashLoop | `kubectl -n genai-demo describe pod -l app=glassbox` and logs | Missing or expired persona keys Secret, or a Secret key that `create_secrets.sh` did not write. Re-run `create_secrets.sh` and restart |
| Site does not answer after `--teardown` | `kubectl -n genai-demo get ingress` | Run `deploy/scripts/deploy.sh` again and wait for the certificate |

## 8. Cost and off switches

| Item | Cost | Off switch |
|---|---|---|
| HTTPS load balancer (while the Ingress exists) | about $18 per month | `demo_down.sh --teardown` |
| Traffic generator (every 5 minutes, 07:00 to 22:00 SGT) | measured average $0.00057 per request, about $3 to $7 per month at the real mix | `demo_down.sh` (suspend) |
| Gemma VM (A100) | about $5 to $6 per hour while running, about $2 for the 23 minute test | `demo_down.sh`, auto stop after 180 minutes. `stop` must use `--discard-local-ssd=false` (the script does) |
| Pods, Vertex monitoring reads, Elastic ingest | negligible | `teardown.sh` scales the app and agent to 0 |
| Static IP | small | keep it, or release manually |

Safety net: the traffic generator has `concurrencyPolicy: Forbid`, a run deadline, a hard cap of 5 requests per run, and the cost alert fires above 0.25 USD per hour.
Current state at the time of writing: the CronJob is suspended and the Gemma VM is stopped.

## 9. Open items

1. Vertex AI integration is incomplete. The `gcp_vertexai` input needs a service account key (`credentials_json`); Workload Identity alone does not work for it. The agent `glassbox-elastic-agent` is enrolled but its `gcp/metrics` component is failed, and the package dashboards have no data. Once Vertex credentials are in place, finish with:
   ```
   gcloud iam service-accounts keys create backend/secrets/glassbox-monitoring-key.json \
     --iam-account=glassbox-monitoring@elastic-sa.iam.gserviceaccount.com
   source backend/.venv/bin/activate
   python -m elastic.fleet --env-file backend/secrets/fleet.env --credentials-file backend/secrets/glassbox-monitoring-key.json
   kubectl -n genai-demo create secret generic glassbox-fleet --from-env-file=backend/secrets/fleet.env --dry-run=client -o yaml | kubectl apply -f -
   kubectl -n genai-demo rollout restart deployment/glassbox-elastic-agent
   ```
   The key command is for the project owner to run (it was not created by automation). The `--credentials-file` option exists only in the uncommitted change to `elastic/fleet.py`; commit it first. Delete the key file after the demo season (`gcloud iam service-accounts keys delete`).
2. Lens rendering of the Glass Box dashboard and the Kibana trace link were checked through REST only. Please eyeball both once in a logged-in browser.
3. Post-login UI visuals were checked by API calls and frontend tests only.
4. Guardrail log export uses project admin keys (see section 5).
5. Gemma `/metrics` is open (accepted risk) and the hardening proposal awaits approval.
