# Deployment notes

## Client IP and rate limits

The backend keys rate limits and the wrong-password lockout on the client IP. Behind the Google load
balancer set `TRUSTED_PROXY_HOPS=1`: the LB appends `<client>, <lb>` to `X-Forwarded-For`, so the entry
second from the right is the client. That position is trusted by contract (it must also parse as an IP,
otherwise the socket peer is used); anything a caller puts further left is ignored.

In-cluster callers (the traffic generator, `kubectl port-forward`) do not pass through the LB, so there
is no trusted hop for them. They can forge `X-Forwarded-For` to pick their own limiter key, which is
acceptable here because the generator makes at most 1-2 requests per 5 minutes and in-cluster access is
already trusted. If untrusted in-cluster callers ever exist, set `TRUSTED_PROXY_HOPS=0` for that
deployment so the socket peer is always used.

## Scripts (run in this order; every script is idempotent and honours `DRY_RUN=1`)

Every script first checks that the gcloud project is `elastic-sa` and (before any cluster change) that the kube
context is `gke_elastic-sa_asia-southeast1-a_kenneth-gke`.

1. `deploy/scripts/gcp_bootstrap.sh`: Artifact Registry repo `glassbox`, global static IP `glassbox-ip`, service
   accounts `glassbox-app` (`roles/aiplatform.user`) and `glassbox-monitoring` (`roles/monitoring.viewer`) with
   Workload Identity bindings for `genai-demo`. No service account keys. Prints the sslip.io host.
2. Image: built by GitHub Actions (`.github/workflows/build-image.yml`) and pushed to Docker Hub `kennethfoo24/glassbox`; take the digest from the run summary. Fallback: `deploy/scripts/build_push.sh` (Cloud Build), where `.gcloudignore` keeps secrets out of the context.
3. Mint ingest-only keys (`docs/dev-tools-mint-ingest-keys.md`), then `deploy/scripts/create_secrets.sh`
   (reads only gitignored local files, prints key names only; refuses admin keys for log export unless `ALLOW_ADMIN_LOG_KEYS=1`).
4. `IMAGE=<image@digest> deploy/scripts/deploy.sh`: renders `deploy/k8s/*.yaml` with `deploy/render.py`, applies, waits
   for the rollout and the managed certificate (up to 90 minutes), then checks `https://<host>/healthz`.
   `WITH_TRAFFICGEN=1` also applies the CronJob, which is created suspended.
5. `deploy/scripts/teardown.sh [--all]`: removes the Ingress and load balancer objects, scales the app to 0;
   `--all` deletes the namespace after you type `delete genai-demo`.

## Boundaries

Only objects in `genai-demo` and the authorized GCP objects above are touched. The app is a client of the existing
daemon collector Service in `opentelemetry-operator-system`; nothing there (or in `o11y-metrics`) is created or changed.
Guardrail prompt logs are exported by the app itself. The hostname depends on the public sslip.io DNS service.

## Cost

The external HTTPS load balancer is about $18 per month; the static IP is small; pods fit on existing nodes; the Gemma
VM costs money only while running. `teardown.sh` stops the load balancer cost; suspending the CronJob stops traffic.

### Measured traffic generator cost (2026-10-05, one hour live, 13 requests)

| Item | Measured |
|---|---|
| Gemini Flash-Lite, answered requests (11) | about $0.000185 each |
| Gemini Flash, answered requests (1) | $0.00539 each |
| Blocked by guardrail (1 of 13) | $0 (no model call) |
| Average per request (13, all included) | $0.00057 |
| Spend for the hour | $0.0074 |

Projection at 1 request per 5 minutes, 07:00 to 22:00 SGT (180 requests per day, about 5,400 per month): about $3 per month at the
observed mix (1 Flash in 13). If Flash is 20 percent of traffic as the design assumes, the blended cost is about $0.0012 per
request, or about $6.6 per month. This is well below the earlier $15 estimate, and the $0.25 per hour alert threshold is never
approached (the rule stayed `ok` with no active alerts).
