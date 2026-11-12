# LLM Observability (Foo Corp HR Assistant)

A demo RAG chatbot that shows Elastic's LLM observability, guardrails, per-persona document security and cost tracking end to end.
Live at https://107-178-251-254.sslip.io (password `demo`), running on GKE `kenneth-gke` (project `elastic-sa`, namespace `genai-demo`).
Internal ids keep the old `glassbox-` prefix (service name, dashboards, k8s objects) so live objects keep working.

## What it does

- **Chatbot:** FastAPI + LangChain (default engine; direct SDK also available) with a React/Vite/Tailwind UI. Two personas (software engineer, manager) with document-level security (DLS) via per-persona Elasticsearch API keys.
- **UI:** a floating sidebar with browser-only conversation history (saved in `localStorage`, newest 50), the model picker (with logos) and the persona switcher (Maya Lim, Daniel Ong, with photos) at the bottom left, answers without bubbles, a pill prompt bar with an icon-only red team menu, and a **View More** tab that slides in the LLM Observability panel (guardrail, security, quality, trace, retrieval, cost). Citation numbers open the cited document in Kibana Discover and carry an illustrative source logo (Confluence, SharePoint, Google Drive, database; the demo documents were indexed by hand). Figtree font, Iconsax icons, Elastic blue; fonts, icons, logos and photos are bundled (no third-party calls at runtime). Works on laptop, tablet and phone.
- **Models:** Elastic Inference Service (GPT-5.4 mini default, Claude 4.5 Haiku, Gemini 3.5 Flash). Self-hosted Gemma on a GPU VM is an on-demand extra (VM currently stopped).
- **Tracing:** OpenTelemetry GenAI spans (prompt and response content captured) for guardrail, retrieval, prompt build, LLM and cost steps, visible in Kibana APM.
- **Guardrails:** inline check in the app plus an ingest pipeline running eland models (prompt-injection DeBERTa, NER DistilBERT, sentiment, zero-shot, language ID), a canary token, and an LLM-as-judge via the EIS `inference` processor. A detection rule in the Security project alerts on flagged prompts.
- **Conversation quality:** negative/positive sentiment, failure to answer, language mismatch and topic relevance scored per exchange.
- **Cost:** per-request cost on the root span (`prices.yaml`), a spend dashboard and an hourly spend alert. General usage alerts (AI tokens and calls, workflow executions, ingested documents) email on budget breaches in all three serverless projects (`docs/RUNBOOK.md`, "Usage and billing alerts").
- **OWASP LLM Top 10:** strong coverage LLM01/02/08/10, partial 04/05/07/09, visibility only 03/06 (see `docs/DEMO.md`).
- **Synthetic data feeder:** a CronJob (every 5 minutes) that backfills and keeps filling the out-of-the-box integration dashboards. All documents are tagged `synthetic` and `synthetic-data-feeder` so they filter out easily. See `docs/feeder.md`.

## Layout

| Path | Contents |
|---|---|
| `backend/app` | API, engines, guardrail and quality pipelines, EIS client, cost |
| `backend/feeder` | Synthetic data feeder (framework, generators per integration group, coverage tool) |
| `backend/trafficgen` | Chat traffic generator CronJob |
| `frontend` | React UI. Develop against the offline backend: `python scripts/dev_stub_server.py` (port 8000; password in the script docstring) and `cd frontend && npm run dev` |
| `elastic` | Dashboards, rules, templates and `python -m elastic.apply --project observability\|security\|search\|all` (`--usage-alerts-only` for just the usage alerts) |
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
- **Ingest is the main remaining cost:** about 100 GB a day (estimate) comes from the `kenneth-gke` cluster (Kubernetes and hostmetrics collectors overlap, about 40 to 55 GB) and the OpenTelemetry demo on it (about 28 GB). Decide: scale the demo to 0 when idle, raise collection periods to 60s, drop the netflow input, set 1 to 3 day retention on noisy streams.
- **Docker log cap on `kenneth-defend-ubuntu`:** `/etc/docker/daemon.json` is written (`max-size` 50m, 3 files) but only applies after a Docker restart or lab redeploy (live-restore is off, so a restart bounces all lab containers). Also consider a disk alert (`system.filesystem.used.pct` above 0.85).
- **Cloud billing alert:** project API keys cannot read billing; set a budget alert in the Elastic Cloud console, or provide a Cloud API key to pull ECU numbers.
- **Rotate exposed credentials:** the project API keys and the lab Fleet enrollment token were printed in a session transcript; rotate them.
- **Hand-made dashboards:** the OWASP Top 10 (`ea67e371-a99e-43ab-b3a8-eb577af00c58`) and Conversation Quality (`c594777c-8647-4005-8b0c-b1fc7f14dbf1`) dashboards the app links to are now saved in `elastic/dashboards/handmade.ndjson` and imported by `python -m elastic.apply --project observability`. The repo-managed `glassbox-owasp` and `glassbox-quality` still exist but the app no longer links to them: decide whether to retire them. The import has been dry-run and unit tested but not yet run live.
- **Placeholder logos (accepted for now):** SharePoint (neutral teal library icon) and Gemma (Gemini mark in Google blue) have no free official logo in the icon set; swap in the official assets if their brand terms allow use in a demo.
- **UI follow-ups (deferred review findings):** viewing an old conversation bumps it to the top of the list; two browser tabs overwrite each other's saved history; one corrupt saved message could blank the app (no per-message validation or error boundary); a saved persona the backend no longer serves is kept; interrupted answers restore as a generic error; selected-answer rule and a few accessibility cues (no h1 below 1024px, rename and delete icons hover-only on touch); the Edit button does not focus the prompt bar; every change re-saves all history synchronously; the offline Gemma hint no longer names the VM to start.
- **Deploy the new UI:** the live site still runs the previous UI image. Build runs in GitHub Actions on push to `main`; deploy by digest once CI is green (see Build and deploy).
- **Visual checks in Kibana** not yet done: Lens panel rendering, the new Discover and Dev Tools links, Dev Tools console URL format.
