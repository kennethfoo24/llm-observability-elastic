# LLM Observability (Foo Corp HR Assistant)

A demo RAG chatbot that shows Elastic's LLM observability, guardrails, per-persona document security and cost tracking end to end.
Live at https://107-178-251-254.sslip.io (password `demo`), running on GKE `kenneth-gke` (project `elastic-sa`, namespace `genai-demo`).
Internal ids keep the old `glassbox-` prefix (service name, dashboards, k8s objects) so live objects keep working.

## What it does

- **Chatbot:** FastAPI + LangChain (default engine; direct SDK also available) with a React/Vite/Tailwind UI. Two personas (software engineer, manager) with document-level security (DLS) via per-persona Elasticsearch API keys.
- **Models:** Elastic Inference Service (GPT-5.4 mini default, Claude 4.5 Haiku, Gemini 3.5 Flash). Self-hosted Gemma on a GPU VM is an on-demand extra (VM currently stopped).
- **Tracing:** OpenTelemetry GenAI spans (prompt and response content captured) for guardrail, retrieval, prompt build, LLM and cost steps, visible in Kibana APM.
- **Guardrails:** inline check in the app plus an ingest pipeline running eland models (prompt-injection DeBERTa, NER DistilBERT, sentiment, zero-shot, language ID), a canary token, and an LLM-as-judge via the EIS `inference` processor. A detection rule in the Security project alerts on flagged prompts.
- **Conversation quality:** negative/positive sentiment, failure to answer, language mismatch and topic relevance scored per exchange.
- **Cost:** per-request cost on the root span (`prices.yaml`), a spend dashboard and an hourly spend alert.
- **OWASP LLM Top 10:** strong coverage LLM01/02/08/10, partial 04/05/07/09, visibility only 03/06 (see `docs/DEMO.md`).
- **Synthetic data feeder:** a CronJob (every 5 minutes) that backfills and keeps filling the out-of-the-box integration dashboards. All documents are tagged `synthetic` and `synthetic-data-feeder` so they filter out easily. See `docs/feeder.md`.

## Layout

| Path | Contents |
|---|---|
| `backend/app` | API, engines, guardrail and quality pipelines, EIS client, cost |
| `backend/feeder` | Synthetic data feeder (framework, generators per integration group, coverage tool) |
| `backend/trafficgen` | Chat traffic generator CronJob |
| `frontend` | React UI |
| `elastic` | Dashboards, rules, templates and `python -m elastic.apply --project observability\|security` |
| `deploy` | k8s manifests and scripts (`deploy.sh`, `demo_up.sh`, `demo_down.sh`, `gemma.sh`, secrets) |
| `scripts` | Seeding, key minting, model import, pipeline install, poison demo |
| `docs` | `RUNBOOK.md`, `DEMO.md`, `feeder.md`, verification notes |

## Build and deploy

GitHub Actions (`.github/workflows/build-image.yml`) runs backend and frontend tests, then pushes `kennethfoo24/glassbox:<sha>` to Docker Hub. Deploy by digest:

```
IMAGE=docker.io/kennethfoo24/glassbox@sha256:<64 hex> bash deploy/scripts/deploy.sh   # also leaves the traffic generator running (WITH_TRAFFICGEN=0 skips it)
```

`deploy.sh` refuses a malformed digest. Full setup and demo steps are in `docs/RUNBOOK.md` and `docs/DEMO.md`.

## Synthetic feeder status (all in `docs/feeder.md`)

| Group | Integrations | Dashboards |
|---|---|---|
| ai | anthropic, anthropic_metrics, claude_code, azure_openai, openai, openai_chatgpt_enterprise, gcp_vertexai | 20 of 25 filled (5 partial: panels use fields the packages never emit) |
| infra | nginx, windows, redis, mysql, kafka, system, Postgres | 44 of 47 filled |
| rest | Palo Alto, Cisco, NetFlow and related network and security sources | 50 of 50 filled |
| devtools | NVIDIA GPU (+ OTel), Cursor, GitLab, Slack | 7 of 8 filled (Cursor panel counts pipeline errors, by design; Slack ships no dashboard) |

Check any time: `cd backend && python -m feeder coverage --group all` (reports EMPTY / PARTIAL / FILLED / STALE per dashboard).

## Pending

- **Deferred dashboards:** Elastic Agent input metrics (~22), Kubernetes controller manager, scheduler, API server and proxy, OTel Collector internal telemetry (7), AWS VPC/ELB OTel, GCP VPC flow OTel, RUM OTel, MongoDB logs, kubernetes_otel partials.
- **Whole-project coverage recheck:** last full count (before devtools) was 81 filled, 32 partial, 31 empty, 50 stale of about 194; rerun the coverage command once ticks have healed the gaps.
- **Friendly hostname:** still the sslip.io address; DuckDNS or an own domain would give a nicer name at no cost.
- **Real AI integration accounts:** the feeder fakes them; decide which have real accounts (Claude Code telemetry is free to wire up).
- **Gemma:** decide on Local SSD (`GEMMA_DISCARD_SSD`) and whether `prices.yaml` should use measured throughput. VM is stopped and its `/metrics` is locked.
- **Visual checks in Kibana** not yet done: Lens panel rendering, the new Discover and Dev Tools links, Dev Tools console URL format.
