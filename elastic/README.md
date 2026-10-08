# Elastic content as code

Apply with `python -m elastic.apply --project observability|security|all [--dry-run] [--only-quality]` (idempotent).
`--alert-override RULE_ID=VALUE` temporarily lowers one quality alert threshold for a proof run; re-run without it to restore.

Existing template mapping changes apply to NEW backing indices only: after changing `FIELD_MAPPINGS`, run
`POST logs-genai_response.otel-default/_rollover` once. `quality.user_sentiment` is the judge's reading of the user's
prompt; `quality.sentiment_label` and `quality.sentiment_score` are the raw eland SST-2 signal, which is binary (neutral
prompts score NEGATIVE), so alerts use `user_sentiment`.

## Observability alert rules (ES|QL, every 5m, look-back 1h)

| Rule id | Name | Fires when | Proves | OWASP |
|---|---|---|---|---|
| glassbox-llm-spend | LLM Observability: LLM spend above threshold | spend over $0.25 in 1h | cost control | LLM10 |
| glassbox-unanswered-rate | LLM Observability: Unanswered rate above 40 percent | at least 5 responses and over 40 percent with `quality.answered == false` | knowledge gaps | quality |
| glassbox-negative-sentiment | LLM Observability: Negative user sentiment | 3 or more `quality.user_sentiment == "negative"` | unhappy users | quality |
| glassbox-low-faithfulness | LLM Observability: Low faithfulness answers | 2 or more `quality.low_faithfulness == true` | judge sees unsupported answers | LLM09 |
| glassbox-restricted-probing | LLM Observability: Restricted topic attempts | 3 or more responses for one persona with `quality.answered == false` and `quality.hidden_count > 0` | users asking about content their role cannot see and getting nothing | LLM08 |
| glassbox-off-topic | LLM Observability: Off topic prompts | 3 or more `quality.off_topic == true` | scope drift | quality |
| glassbox-language-mismatch | LLM Observability: Language mismatch | 2 or more `quality.lang_mismatch == true` | answer language differs from prompt | quality |

Limit: `hidden_count` counts catalog matches (RRF top 8), not relevance, so it only means something together with `answered == false`.
Rules have no actions (they fire silently and show in Kibana).

## Security detection rules (KQL on `logs-genai_response*`, every 1m)

| Rule id | Query | Severity | OWASP |
|---|---|---|---|
| glassbox-flagged-prompts | guardrail verdict FLAGGED | high | LLM01 |
| glassbox-llm02-pii-in-response | `output_reasons : "pii_in_response"` | high | LLM02 |
| glassbox-llm05-unsafe-output | `output_reasons : "unsafe_markup"` | medium | LLM05 |
| glassbox-llm07-system-prompt-leak | `output_reasons : "system_prompt_leak"` | high | LLM07 |

## Dashboards (Observability)

| Id | Title | Content |
|---|---|---|
| glassbox-overview | LLM Observability: Overview | cost, tokens, guardrail verdicts, latency |
| glassbox-quality | LLM Observability: Conversation quality | two full width list tables first (answered prompts, responses and flags; blocked and flagged guardrail prompts), then answered rate, top unanswered prompts, sentiment, language mismatch, topics, off topic rate, faithfulness, relevance, flagged reasons |
| glassbox-owasp | LLM Observability: OWASP LLM Top 10 coverage | live evidence per risk (LLM01, 02, 05, 07, 08, 09, 10), model usage for LLM03 and LLM06 (visibility only), risk to control table |

## Document scan demo (LLM04, indirect LLM01)

`python -m elastic.apply --project observability` installs the `genai-doc-scan` pipeline, creates the separate
`hr-kb-staging` index (only if absent; the live `hr-kb` is never touched) and the alert `glassbox-doc-integrity`.
`python scripts/poison_demo.py` indexes a clean pair, a poisoned document and a tampered copy and prints the
verdicts; the alert then fires within 5 minutes. Clear it with `python scripts/poison_demo.py --cleanup`
(removes only the demo documents; the alert recovers on its next run). Documents longer than 2000 characters are
scanned in up to 4 chunks (max injection probability wins).
