# CLAUDE.md

Demo RAG chatbot "Foo Corp HR Assistant" (product name LLM Observability) showing Elastic LLM observability, guardrails, DLS and cost. See `README.md` for the overview and what is pending.

## Conventions
- Internal ids keep the `glassbox-` prefix (service name, dashboards, k8s objects, images). Do not rename them.
- Elastic Serverless: Observability project (GCP) holds everything; Security project (AWS) holds the detection rule. `python -m elastic.apply` needs `--project observability|security`.
- The app links to two hand-made Kibana dashboards (OWASP Top 10 `ea67e371-a99e-43ab-b3a8-eb577af00c58`, Conversation Quality `c594777c-8647-4005-8b0c-b1fc7f14dbf1`); they live in `elastic/dashboards/handmade.ndjson` and are imported by `elastic.apply` (Observability only). Conversation history is browser-only (`localStorage`), never server-side.
- Never commit secrets: `elasticsearch.txt`, `backend/secrets/`, `*.env` are gitignored. `.superpowers/` is gitignored scratch; never add it.
- Never print the demo password or any API key in output.

## Commands
- UI development: `python scripts/dev_stub_server.py` (offline backend on :8000, no Elastic or EIS) plus `cd frontend && npm run dev`. The UI bundles its fonts, icons, logos and photos; never add runtime calls to third-party hosts.
- Backend tests: `cd backend && pytest -q` (feeder volume tests are slow; they carry `@pytest.mark.timeout(240)`).
- Elastic and deploy tests: `pytest -q elastic deploy`. Frontend: `cd frontend && npm ci && npm run typecheck && npm test`.
- Deploy: build runs in GitHub Actions; deploy by digest with `IMAGE=docker.io/kennethfoo24/glassbox@sha256:<64 hex> bash deploy/scripts/deploy.sh` (it applies the traffic generator CronJob unsuspended, so deploy means traffic on). Wait for CI success before deploying; never deploy with an empty digest.
- Usage alerts (AI tokens, workflows, ingest; email, all three projects): `python -m elastic.apply --project all --usage-alerts-only`. The Search project only ever gets these rules. Billing is not readable with a project key.
- Feeder: `cd backend && python -m feeder coverage --group all`; ticks run via the `synthetic-data-feeder` CronJob. Uses a narrow API key named `synthetic-data-feeder`.

## Feeder rules (`backend/feeder`)
- Generators are deterministic; `engine.generate` sets `@timestamp` to the bucket minute and adds the `synthetic` tags. Use `infra.counter`/`infra.LoadRate` for monotonic counters.
- TSDB streams refuse custom `_id` (add the prefix to `engine.NO_ID_PREFIXES`); duplicate timestamps per dimension set collide.
- Add a group by registering in `registry` and covering it with an offline test in `backend/tests`; document it in `docs/feeder.md`.

## Working agreements
- The user decides outward-facing and shared-resource actions (merging, pushing to shared branches, cluster changes beyond the demo namespace); explicit chat approval is required, and a permission denial is not to be worked around.
- Deferred work and open decisions are listed under "Pending" in `README.md`; keep that list current.
- Docs: `docs/RUNBOOK.md` (operations), `docs/DEMO.md` (demo flow, OWASP map), `docs/feeder.md` (feeder).
