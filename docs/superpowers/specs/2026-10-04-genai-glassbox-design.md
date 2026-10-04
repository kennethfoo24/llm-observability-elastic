# "Elastic GenAI Glass Box": Workplace HR RAG chatbot with end-to-end LLM Observability, Security and Cost

## Context
The goal is a polished, interactive demo app for customers. It shows Elastic's LLM Observability story across four pillars:
1. Out-of-the-box (OOTB) LLM dashboards.
2. Step-by-step OTel LLM tracing that captures prompt and response content.
3. AI guardrails: an ingest pipeline running eland-imported Hugging Face models, plus a detection rule.
4. Predictable AI cost tracking and alerting.

It also shows document-level security (DLS) as you swap personas. The design is inspired by elasticsearch-labs `chatbot-rag-app`, but rebuilt from scratch so the trace waterfall and the UI read cleanly.

**Constraints and decisions, confirmed with the user**
- No OpenAI key. The cheapest way to get the most OOTB dashboards is **Vertex AI Gemini** in the `elastic-sa` project:
  - The Elastic GCP Vertex AI integration supplies the dashboards.
  - Expected spend is about $2/month for demos and about $13/month with the traffic generator.
- **Self-hosted Gemma 4 31B** on the existing `gemma-llm` VM (A100, vLLM, about $5–6/hr) is an on-demand third model. In P0, rename the VM to **`kenneth-gemma-llm`**: run `gcloud compute instances set-name` while it is TERMINATED, then check that the startup script, firewall tags and labels don't reference the old name. The vLLM hostname is IP-based (`llm-34-126-172-79.nip.io`), so the rename doesn't affect it. Check whether the external IP is static; if it isn't, reserve one.
- Theme: **Workplace HR**, close to the Elastic sample app.
- Topology:
  - Everything runs in the **Observability** Serverless project: corpus, DLS, telemetry, guardrail models and pipeline.
  - The **Security** project reaches Observability data through **cross-project search (CPS, now GA)** to run the detection rule.
  - Fallback if CPS doesn't work for detection rules: an OTel collector fans the guardrail log stream out to Security, with the models and pipeline installed there too.
  - The Search project is not used.
- Guardrails run **both inline** (an app span that blocks the request) **and asynchronously** (ingest pipeline verdict, then the detection rule).
- Stack: FastAPI with direct SDKs **and** LangChain, selectable per request through an "Engine" toggle. Frontend: React, Vite and Tailwind.
- UI: light app styled like elastic.co (blue `#0B64DD`, ink `#0E1B35`, pink `#F04E98`, yellow `#FEC514`, Space Mono for telemetry), with a **dark "X-ray" drawer** under each answer.
- Deployment: GKE `kenneth-gke`, namespace `genai-demo`, public HTTPS through GKE Ingress on sslip.io, behind a shared-password gate.
- A traffic-generator CronJob runs every 5 minutes.

## Architecture
```
Browser (React) ──HTTPS/SSE──> FastAPI (EDOT Python + OTel GenAI instrumentations)
  POST /chat  [root span: app.persona, app.genai.engine, app.genai.model, app.genai.cost_usd]
   ├─ guardrail.check   → ES _infer: prompt-injection + NER (parallel, 1.5s timeout, fail-open+flag)
   ├─ retrieval.hybrid  → ES retriever API using the persona's DLS API key:
   │                      rrf(semantic_text[ELSER via EIS], BM25) → text_similarity_reranker(.jina-reranker-v3)
   │                      + catalog-key query (FLS: title/classification only) → "hidden by DLS" ghost cards
   ├─ prompt.build      → context enrichment (citations, persona system prompt)
   ├─ LLM call          → Direct: google-genai(vertexai=True) | openai→vLLM Gemma
   │                      LangChain: LCEL retriever→prompt→ChatGoogleGenerativeAI/ChatOpenAI (SDK span nested)
   └─ cost.compute      → prices.yaml (incl. Gemini thinking tokens; Gemma = GPU-hr amortised)
  + OTel log record: data_stream.dataset=genai_guardrail (prompt, persona, model, trace.id)
        │ OTLP → existing opentelemetry-kube-stack daemon collector → Obs managed OTLP
        ▼
Elastic Observability: APM traces (SPAN_ONLY content), logs@custom → genai-guardrail pipeline
        ▼ CPS
Elastic Security: ES|QL detection rule on security.threat_verdict == "FLAGGED"
```

**Instrumentation choices.**
- Use the official `opentelemetry-python-genai` packages: `opentelemetry-instrumentation-google-genai`, `-genai-openai` and `-genai-langchain`.
- Turn off EDOT's openai instrumentation with `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS`.
- Set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY`.
- Bake the packages into the app image and start with `opentelemetry-instrument`. Don't use operator injection.
- Calculate cost **once**, on the root span, so LangChain mode never counts tokens twice.

**Guardrail pipeline (`genai-guardrail`).** `logs@custom` routes to it conditionally, only when the dataset is `genai_guardrail`. Steps:
1. Inference: `protectai/deberta-v3-base-prompt-injection-v2` (text_classification).
2. Inference: `elastic/distilbert-base-cased-finetuned-conll03-english` (ner). This replaces the model in the original request, which doesn't exist on Hugging Face.
3. Regex/grok: email, phone, SSN/NRIC, salary figures.
4. Painless script: sets `security.threat_verdict` to CLEAN or FLAGGED, plus `security.threat_reasons[]` and the scores.
5. `on_failure`: verdict = UNKNOWN.

Models are imported with the eland Docker image and use adaptive allocations.

**DLS.**
- The `hr-kb` index holds about 40 synthetic markdown docs with `allowed_roles` and `classification` fields.
- Personas: Employee, Manager, HR Partner, Executive.
- Each persona gets its own API key, minted with a role-descriptor DLS query. Keys are stored in a Kubernetes Secret.
- A separate FLS-limited "catalog" key supplies ghost-card titles without exposing restricted content.

## Phases
- **P0, risk tests (do these first and record results):**
  - Confirm the Gemini 3.x model IDs with real `generateContent` calls on `global` and `asia-southeast1`. Pick the newest GA Flash-Lite and Flash; avoid previews.
  - Check that SPAN_ONLY content and token attributes, including thinking tokens, appear in APM.
  - Check how LangChain and SDK spans nest.
  - Find which index a dataset-tagged OTel log actually lands in (Wired Streams is on), and whether `logs@custom` fires.
  - Do the eland import and `_infer` latency on Serverless.
  - Find the minimum privileges a persona key needs for semantic search and reranking.
  - Test a CPS link plus an ES|QL detection rule. This needs an Elastic Cloud API key. Fall back to fan-out if it fails.
  - Check Vertex request-response logging to BigQuery.
  - Measure Gemma cold start.
- **P1:** corpus generation, the `hr-kb` mapping, and `scripts/seed_index.py` plus `mint_persona_keys.py`.
- **P2:** backend:
  - Endpoints: `/chat` over SSE, `/personas`, `/models`, `/health/gemma`.
  - Spans: guardrail, retrieval, prompt, LLM (SDK and LangChain), cost.
  - A circuit breaker for Gemma, with a "Start Gemma" hint in the UI.
- **P3:** import the guardrail models, create the pipeline and `logs@custom` hook, and add the Red-team prompt bank. Inline blocking shows a block card.
- **P4:** cost: `prices.yaml`, root-span attributes, and an ES|QL cost panel.
- **P5:** UI. Build it with the **`design-taste-frontend`** skill (user's choice), using elastic.co brand tokens. Contents:
  - Persona avatar cards; model and engine switches; a Red-team button.
  - The X-ray drawer: mini waterfall, docs with scores, ghost cards, tokens and $, verdict, latency, and a Kibana link `/app/apm/link-to/trace/{traceId}`.
- **P6:** deployment:
  - Images go to Artifact Registry.
  - Namespace `genai-demo`, with Workload Identity mapped to a Google service account holding `aiplatform.user`.
  - Ingress with a ManagedCertificate on sslip.io, and the password gate as middleware.
  - Rotate the plaintext OTLP key in `o11y-metrics/chatbot-rag-app` and move it into a Secret.
- **P7:** dashboards and alerts:
  - The Vertex AI integration: a service-account JSON key with `monitoring.viewer`; an audit-log sink to Pub/Sub; and prompt/response logs in BigQuery.
  - The APM GenAI views.
  - Custom dashboards: cost by model, persona and engine; guardrail verdicts; vLLM Prometheus metrics, scraped locally on the VM.
  - K8s and GCE infrastructure dashboards.
  - Kibana rule: rolling 1-hour cost above threshold.
  - The CPS detection rule in Security.
- **P8:** traffic-generator CronJob every 5 minutes: about 85% benign, 10% injection, 5% PII. It rotates personas and models, and uses Gemma only when the VM is up.
- **P9:** `docs/RUNBOOK.md` and a demo script: VM start/stop, model warm-up, reset, and a 10-minute demo flow covering all four pillars.

## Repo layout (new)
`backend/app/{main,config,guardrail,retrieval,llm_sdk,llm_langchain,cost,telemetry}.py`, `backend/prices.yaml`, `frontend/src/...`, `data/corpus/*.md`, `scripts/*`, `elastic/{pipelines,templates,rules,dashboards}/*.json`, `k8s/*.yaml`, `trafficgen/`, `docs/`.

## Process after approval
1. Write this design as the spec in `docs/superpowers/specs/2026-10-04-genai-glassbox-design.md`, together with a git init and the first commit.
2. User reviews the spec.
3. Invoke `superpowers:writing-plans` for the detailed task plan.
4. Execute, starting with the P0 risk tests.

## Verification
- **Pillar 1:** the Vertex AI integration dashboard shows Gemini request and token metrics within about 6 minutes of traffic. The infrastructure dashboards link from the APM service.
- **Pillar 2:** one chat produces an APM waterfall: HTTP POST → guardrail.check → retrieval.hybrid (ES spans) → prompt.build → chat span with `gen_ai.input.messages` and `gen_ai.output.messages` and token usage. Repeat in LangChain mode and confirm the nested spans.
- **Pillar 3:** the Red-team injection prompt is blocked in the UI. The guardrail log document has `security.threat_verdict: FLAGGED`. A Security alert fires within one rule interval through CPS (or the fallback).
- **Pillar 4:** `app.genai.cost_usd` on the root span matches a hand calculation from the token counts. Lowering the threshold fires the cost alert.
- **DLS:** the same question returns different citations and ghost-card counts for Employee and Executive. A direct `_search` with the Employee key returns no restricted docs.
- **Ops:** with the Gemma VM stopped, the UI shows "offline" gracefully. The CronJob runs green, and the public URL needs the password.

## Cost model (monthly, at demo scale plus 5-minute traffic)
| Item | Where it's billed | Estimate |
|---|---|---|
| Eland guardrail models (DeBERTa and DistilBERT) running in the **Observability** project | Elastic Serverless. Observability and Security projects are **not charged for ML compute (VCUs)**, only for ingest and retention. Search projects are the ones billed ML VCUs. | **$0 for compute.** Limit: Observability and Security projects allow fewer ML allocations (Low: 0–2), which is plenty here. Models scale to zero after 24 hours idle. |
| Guardrail logs and traces with prompt content | Observability ingest (about $0.09/GB) and retention (about $0.019/GB-month) | about 0.2–0.5 GB/month, **under $0.10** |
| ELSER embeddings and Jina reranker via EIS | Elastic Inference Service, per token | about 40 docs once, plus queries: **cents** |
| CPS (Security origin → Observability linked) | Billed to the Security project since **2026-09-16**, based on the linked project's *total* retained volume plus query egress | Depends on everything stored in the Observability project, not only this demo. Check in the Serverless estimator during P0; if it's material, use the collector fan-out instead. |
| Vertex Gemini | GCP | about $2 (demos), about $13 with the traffic generator |
| Vertex integration plumbing (Pub/Sub, BigQuery, Monitoring API) | GCP | under $1 |
| GKE workloads (2 small pods + CronJob) | existing cluster | $0 extra |
| Gemma VM (A100) | GCP | about $5–6 per *running* hour; on demand only |

## Open items, handled in P0
- The CPS billing rate for the Observability project's current retained volume. This decides CPS versus fan-out.
- Final Gemini model IDs and prices.
- Whether the VM rename has side effects (startup script references, static IP).
