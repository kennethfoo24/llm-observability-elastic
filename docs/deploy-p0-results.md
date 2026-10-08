# Deployment Phase 0 results (2026-10-05)

Evidence for Tasks 3, 4, 6, 7 of `docs/superpowers/plans/2026-10-05-deploy-dashboards-alerts.md`. No secrets are recorded. Spike scripts: `scripts/spikes/deploy/`.

## Established earlier on 2026-10-05 (not redone)

- The gateway secret of `opentelemetry-kube-stack-*` points at `kenneth-sandbox-d54ee0` (our Observability project).
- A probe LOG with `data_stream.dataset=genai_guardrail` sent through the daemon collector never arrived within 30 minutes; the gateway logs `bulk indexer flush error` and writes logs to the fixed index `logs.otel`. Therefore guardrail logs bypass the shared stack and are exported directly by the app.

## A. Security routing (same probe against both projects)

`sec_log_routing.py [security|observability]` sent one OTLP/HTTP JSON log with `data_stream.dataset=genai_guardrail` and `genai.prompt_text` to each managed OTLP endpoint: both returned 200.

| | Security | Observability (control) |
|---|---|---|
| Landed in | `.ds-logs-genai_guardrail.otel-default-2026.10.05-000001` | `.ds-logs-genai_guardrail.otel-default-2026.10.04-000001` |
| `data_stream` | type `logs`, dataset `genai_guardrail.otel`, namespace `default` | identical |
| Dataset honoured | yes (the managed OTLP endpoint appends `.otel`) | yes |
| Prompt text field path | `attributes.genai.prompt_text` (dotted key, flat in `attributes`) | same |
| Body | `body.text` | same |
| Enriched by guardrail pipeline | no (pipeline absent) | yes (`attributes.security.*`, e.g. `injection_score`, `models_ok`) |
| `logs@custom` pipeline | 404 (does not exist yet) | exists (probe hook -> `genai-guardrail`, ignore_failure) |
| `genai-guardrail` pipeline | 404 | exists |
| ML models | only `.elser_model_2_linux-x86_64`, `lang_ident_model_1` | adds `protectai__deberta-v3-base-prompt-injection-v2`, `elastic__distilbert-base-cased-finetuned-conll03-english` |

Result: the Security project routes identically, so Task 3 can create `genai-guardrail` plus the `logs@custom` hook there exactly as in Observability. The key has `manage_pipeline`, `manage_ml`, `manage_index_templates` cluster privileges in Security (checked with `_security/user/_has_privileges`). The two models must be imported there first (Task 3). No design change.

## B. `gcp_vertexai` 1.5.0 integration inputs (Fleet manifest, read-only)

- Policy templates: `GCP Vertex AI Metrics` (input `gcp/metrics`); `GCP Vertex AI Logs` (inputs `gcp/metrics`, `gcp-pubsub`).
- Package-level vars: `project_id` (required, not secret), `credentials_file` (optional), `credentials_json` (optional). None is flagged `secret`.
- Data streams: `gcp_vertexai.metrics` (vars `period` required, `exclude_labels`, `regions`), `gcp_vertexai.auditlogs` (pubsub: `topic`, `subscription_name`, `subscription_create`, ... required), `gcp_vertexai.prompt_response_logs` (`table_id` required, BigQuery).
- Credentials decision: NO JSON key is mandatory. Both credential vars are optional in the manifest, so the metrics stream can run on Application Default Credentials. Plan: single agent pod with Workload Identity (KSA `glassbox-monitoring` -> GSA `glassbox-monitoring`, `roles/monitoring.viewer`), only `project_id` and `period` set, credential vars left empty. Residual risk: the manifest says optional but does not prove ADC works end to end for this input; Task 7 must verify the first metrics doc arrives (3-6 min lag). If ADC fails, STOP and ask the user (a service account key is not authorised).
- Use only the metrics data stream (audit logs and prompt/response logs need Pub/Sub or BigQuery, out of scope).

## C. Trace attributes and ES|QL (Observability, `traces-generic.otel-default`)

Serverless returns 410 for `_mapping/field`, and `/api/saved_objects/_find` is unavailable too. Types below come from ES|QL column metadata (`FROM ... | KEEP ... | LIMIT 0`).

Data still exists: 180 `glassbox-backend` spans, 2026-10-04 10:06 to 10:15 UTC; 13 carry `cost_usd`. Retention may age this out; re-run `trace_mapping.py` in Task 5.

| Field | Type |
|---|---|
| `attributes.app.genai.cost_usd` | double |
| `attributes.app.genai.input_tokens` | long |
| `attributes.app.genai.output_tokens` | long |
| `attributes.app.genai.thinking_tokens` | NOT mapped yet (no span has it; from the backend code, re-verify in Task 5) |
| `attributes.app.persona`, `app.genai.model`, `app.genai.engine`, `app.genai.cost_basis`, `app.guardrail.verdict`, `app.guardrail.status` | keyword |
| `attributes.app.blocked` | boolean |
| `attributes.guardrail.verdict` | not present as a column (`attributes.guardrail.status`, `.injection_score` double, `.latency_ms` long, `.person_count`, `.reasons` exist) |

Dynamic mapping rule for numerics: native OTLP numerics are typed (int -> long, double -> double, bool -> boolean), not keyword or flattened; confirmed on the otel-demo attributes (`app.order.amount` double, `app.products.count` long, `app.shipping.amount` double, `app.guardrail`-style fields as above). Caveat: a field whose first-seen value was a string stays keyword forever (`attributes.app.payment.amount` is keyword), so `TO_DOUBLE` is NOT needed for the LLM Observability fields but is harmless; the app must always emit `cost_usd` as a float, never a string. Filter field `service.name` is correct.

Working ES|QL, unchanged from the brief (no casts):

```
FROM traces-generic.otel-default | WHERE service.name == "glassbox-backend" AND attributes.app.genai.cost_usd IS NOT NULL | STATS requests = COUNT(*), spend = SUM(attributes.app.genai.cost_usd) BY attributes.app.genai.model | LIMIT 10
```
Result: one row, `gemini-3.1-flash-lite`, 13 requests, spend 0.000781 (double). In ES|QL a reserved word cannot be a column alias (`first` failed to parse; use `oldest`/`newest`).

## D. Dashboard template route

Route: read-only extraction from an existing dashboard (no Playwright, no new Kibana object, `glassbox-template-esql` was not created). Reasons: in this Kibana, Lens panels are stored by value inside dashboards (`_export` of type `lens` returns 0 objects; `_find` is unavailable on Serverless), so the template is one inline panel: dashboard `Trading Operations`, panel `Shares Traded Per Symbol` (type `lens`, `lnsXY` line chart, `textBased` ES|QL datasource, one metric, a date bucket x axis and one split column). 141 of 176 dashboards use ES|QL panels.

Files: `elastic/dashboards/template.lens-esql.json` (the panel; `panelIndex`, `gridData.i` and `appliedTimeRange` removed) and `elastic/dashboards/template.meta.json` (RFC 6901 pointers verified against the file: `panel_title`, `esql_string`, `esql_string_state_query`, `x_column`, `y_column`, `split_column`, `visualization_type`, `series_type`, `layer_id`, `datasource_columns`, `ad_hoc_data_view`, `grid`).
Substitution notes for Task 4: the ES|QL appears twice (layer query and `state.query`); column names must match in `datasource_columns` (columnId, fieldName, label, meta), the visualization accessors and the layer; the ad hoc data view (type `esql`, id = hash of the index pattern) must be rebuilt for the new `FROM` target; time bucketing uses `BUCKET(@timestamp, 100, ?_tstart, ?_tend)`; `TS` command is used there for a metrics index, use `FROM` for traces/logs.

## E. Collector, image and load balancer facts

1. Trace probe through the existing daemon collector: `kubectl port-forward svc/opentelemetry-kube-stack-daemon-collector 14318:4318`, one OTLP/HTTP JSON trace (`/v1/traces`, service `deploy-p0-trace-probe`) returned 200 and was found in `.ds-traces-generic.otel-default-2026.09.29-000008` within 1 s of the first query (arrival under about 15 s). The daemon collector is a valid TRACES target. Port-forward stopped; nothing in `opentelemetry-operator-system` was touched.
2. GKE HTTP load balancing: `addonsConfig.httpLoadBalancing.disabled` prints empty, so it is enabled; the built-in `gce` Ingress controller works by annotation (`kubectl get ingressclass` is empty, expected).
3. Elastic Agent images in the cluster: `fleet-agents/elastic-agent-k8s` DaemonSet `elastic-agent:9.5.0`; `kube-system/elastic-agent` 9.4.3; shared OTel collectors 9.4.2 (daemon) and 9.5.0 (gateway, cluster-stats). Observability project (Kibana and Elasticsearch) is 9.6.0 (Serverless). Pin the new Vertex agent to `docker.elastic.co/elastic-agent/elastic-agent:9.5.0` (same as `fleet-agents`, not newer than the stack).
4. Cloud Build default SA `1059491012611@cloudbuild.gserviceaccount.com` already has `roles/artifactregistry.writer` (and `admin`, `cloudbuild.builds.builder`, `logging.logWriter`); compute default SA `1059491012611-compute@developer.gserviceaccount.com` also has `roles/artifactregistry.writer`, `roles/aiplatform.user`. No IAM change or `--service-account` needed for Task 5 pushes. (Project number 1059491012611.)

## F. Open questions for the user

1. Typed guardrail fields need `logs-otel@custom` mapping plus rollover in each project (Section E of `docs/p0-results.md`). Apply it? Needed only for numeric guardrail panels; the plan works without it using keyword counts.
2. (Informational) If the ADC path for `gcp_vertexai` fails in Task 7, a service account key would be needed and requires the user's explicit approval.
