# OWASP LLM Top 10 coverage and conversation quality: design

Status: approved by the user on 2026-10-07 ("go"). Build only what runs inside Elastic and shows Elastic's value. App-side blocking code that does not show Elastic's value is out of scope.

## Goal

Extend the Glass Box demo so that, for each OWASP LLM Top 10 risk Elastic can address, there is an Elastic-run control, a detection or alert, and evidence in the trace. Add conversation quality checks (sentiment, failure to answer, language mismatch, topic relevancy) and an LLM judge, all scored inside Elastic.

## Coverage map (what is built)

| Risk or check | Elastic mechanism | Output |
|---|---|---|
| LLM01 prompt injection (direct, existing) | eland DeBERTa in `genai-guardrail` | existing verdict and rule |
| LLM01 indirect injection, LLM04 poisoning | `genai-doc-scan` ingest pipeline: `fingerprint` processor plus DeBERTa on document text; demo in a separate staging index | `doc_scan.verdict`, alert rule |
| LLM02 disclosure | `genai-quality` on the RESPONSE: regex PII (reuse `PII_PATTERNS`) plus NER model | `output_verdict` FLAGGED reason `pii_in_response`, Security rule |
| LLM05 improper output | `genai-quality` Painless match for script/iframe/javascript:/data:text/html/event handlers/markdown links | reason `unsafe_markup`, Security rule |
| LLM07 system prompt leakage | canary token in the system prompt, matched by `genai-quality` (the canary is a deploy-time secret held in backend/secrets, never committed) | reason `system_prompt_leak`, Security rule |
| LLM08 vector and embedding weaknesses | existing DLS, plus per-query `hidden_count` and `top_hidden_score` logged; ES|QL panel and probe alert | alert `restricted-topic probing` |
| LLM09 misinformation | EIS LLM judge via the ingest `inference` processor on a completion endpoint (a different vendor than the answering model: `.anthropic-claude-4.5-haiku-completion`), plus citation validity and reranker score | `quality.faithfulness` 1..5, `quality.relevance` 1..5, alert on low faithfulness |
| LLM10 unbounded consumption | existing tracing token and cost data, cost alert, rate limits | existing |
| Sentiment (negative and positive) | eland sentiment model on the prompt | `quality.sentiment` |
| Failure to answer | app flag `answered` plus judge | `quality.answered`, unanswered-rate alert, top unanswered prompts |
| Language mismatch | built-in `lang_ident_model_1` on prompt and response | `quality.prompt_lang`, `quality.response_lang`, `quality.lang_mismatch` |
| Topic relevancy | eland zero-shot classifier on the prompt with HR topic labels plus `off_topic` | `quality.topic`, `quality.off_topic` |

Out of scope by decision: LLM03 supply chain and LLM06 excessive agency (visibility only: the trace shows `gen_ai.response.model`); inline output blocking and extra UI sanitising (the UI already neutralises HTML).

## Mechanism

1. After a successful (not blocked) answer the app emits ONE OTel log record, dataset `genai_response`, through the existing direct guardrail log exporter (both Elastic projects). Fields (flat dotted attribute keys, like the prompt log): `genai.prompt_text`, `genai.response_text`, `genai.context_text` (retrieved snippets, truncated to 6000 chars), `genai.retrieved_ids`, `genai.cited_ids`, `genai.top_score`, `genai.hidden_count`, `genai.top_hidden_score`, `genai.answered`, `app.persona`, `app.genai.model`, `app.genai.engine`; `trace_id`/`span_id` come from the active span, so the log correlates with the trace.
2. Ingest pipeline `genai-quality`, hooked in `logs@custom` with an `if` on dataset `genai_response` (merge, never drop existing processors), runs: dot_expander, lang_ident on prompt and response, sentiment on prompt, zero-shot topic on prompt, NER and regex on response, canary and markup scripts, the judge (a `script` builds the judge prompt into one field, the `inference` processor calls the EIS completion endpoint, a `json` processor parses the answer with `ignore_failure`), then one Painless verdict script writing `output_verdict`, `output_reasons`. Every model step has `ignore_failure` and the verdict degrades to UNKNOWN rather than failing the document.
3. Typed fields: the otel logs mapping flattens `attributes.*`, which blocks ES|QL on sub-keys (see docs/p0-results.md). Create our own component template and index template for `logs-genai_response.otel-*` (priority above the default, composed of the default otel components plus ours) that maps the result fields as top-level typed fields (keywords, doubles, booleans), in both projects. These are new objects owned by this project; do not edit shared templates (`logs@custom` hook merge is the only edit to a shared object, as before).
4. Security project gets a subset pipeline (regex, NER, canary, markup, verdict; no sentiment/topic/judge); Observability gets the full pipeline. Models: sentiment `distilbert-base-uncased-finetuned-sst-2-english` and zero-shot `typeform/distilbert-base-uncased-mnli` imported with eland into Observability only (ML compute is not billed in these project types); NER and DeBERTa already exist in both.
5. Rules, alerts and dashboards as code under `elastic/`: Security detection rules (LLM02, LLM05, LLM07), Observability alert rules (unanswered rate, negative sentiment share, low faithfulness, restricted-topic probing, document scan FLAGGED), dashboards `Glass Box: Conversation quality` and `Glass Box: OWASP LLM Top 10 coverage` (a table of risk, Elastic control, live evidence counts).
6. UI (LLM Observability panel): new "Output guardrail and quality" section showing, per answer, what Elastic scores asynchronously: a "Try it in Dev Tools" link that prefills `POST _ingest/pipeline/genai-quality/_simulate` with this answer's prompt, response and context (the presenter runs it live), a link to the response log in Discover by trace id, a link to the Conversation quality dashboard, and OWASP chips (LLM02/05/07/09) explaining which risk each finding maps to. No new app-side Elasticsearch read key is introduced. The red-team menu gains one prompt per new risk (system prompt extraction, markup output, off-topic, non-English, rude, praise).
7. Document scan demo (LLM04, LLM01 indirect): `scripts/poison_demo.py` indexes a clean and a poisoned document into the separate index `hr-kb-staging` through `genai-doc-scan`; the live `hr-kb` is never modified by the demo.

## Constraints (inherit)

No secrets in the repo (the public GitHub repo kennethfoo24/llm-observability-elastic); no hostnames of Elastic projects in source; no em or en dashes in user-visible text; every commit ends with the Co-Authored-By trailer; do not touch other namespaces, `o11y-metrics`, or the shared collector; no service-account keys; the CronJob stays suspended; Gemma stays stopped; Docker Hub image built by GitHub Actions, deployed with `deploy/scripts/deploy.sh`.

## As built (final review, 2026-10-07)

- Judge: Claude Haiku through EIS. Different vendor than the default answerer only; when Claude Haiku is the selected answerer the same vendor judges. Judge JSON: faithfulness, relevance, answered, `sentiment` (positive, neutral, negative; typed `quality.user_sentiment`) and `on_topic` (typed `quality.on_topic`, drives `quality.off_topic`). The eland sentiment model is binary and kept only as the raw signal (`quality.sentiment_label`, `quality.sentiment_score`). The zero-shot topic remains the raw `quality.topic` and the off topic fallback only when the judge failed AND the prompt is English.
- Language mismatch is set only when both detections have probability of at least 0.8 and the prompt has at least 25 characters; an English function word check overrides lang_ident confusions on short English prompts (a heuristic with known errors in both directions).
- Judge context fidelity: the judge sees the same document text the answering model saw (3000 characters per document, 12000 for the whole context, logged as `genai.context_text`). The same string is returned in the chat response as `quality_context` and used by the Dev Tools simulate link.
- Judge hardening: per-document random delimiters, instructions to ignore anything inside them, strict single-object parsing. Residual risk: the judge is an LLM and can be manipulated; PII, markup and canary checks are deterministic and unaffected; judge scores are advisory.
- Verdict degradation: a failed markup or canary check gives `UNKNOWN`, not `CLEAN`.
- LLM08: an attempt is `quality.answered == false` with `quality.hidden_count > 0`, 3 or more per persona per hour. `hidden_count` counts catalog matches (RRF top 8), not relevance.
- Canary visibility: readable in the pipeline definition and in captured system messages; accepted for a demo canary (it detects leakage in the response). Rotation: delete the secret file, re-run create_secrets.sh, redeploy and re-run `elastic.apply`.
- Data path: context copies restricted-persona content into `logs-genai_response*` without document level security; restrict access and consider short retention.
- Out of scope remains LLM03 and LLM06 (visibility only: `gen_ai.response.model` in traces).
