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
| glassbox-llm-spend | Glass Box: LLM spend above threshold | spend over $0.25 in 1h | cost control | LLM10 |
| glassbox-unanswered-rate | Glass Box: Unanswered rate above 40 percent | at least 5 responses and over 40 percent with `quality.answered == false` | knowledge gaps | quality |
| glassbox-negative-sentiment | Glass Box: Negative user sentiment | 3 or more `quality.user_sentiment == "negative"` | unhappy users | quality |
| glassbox-low-faithfulness | Glass Box: Low faithfulness answers | 2 or more `quality.low_faithfulness == true` | judge sees unsupported answers | LLM09 |
| glassbox-restricted-probing | Glass Box: Restricted topic probing | 3 or more queries with `hidden_count >= 3` and `top_hidden_score > 0` for one persona | probing of document-level-security content | LLM08 |
| glassbox-off-topic | Glass Box: Off topic prompts | 3 or more `quality.off_topic == true` | scope drift | quality |
| glassbox-language-mismatch | Glass Box: Language mismatch | 2 or more `quality.lang_mismatch == true` | answer language differs from prompt | quality |

Limit: `top_hidden_score` is an RRF rank score (small, rank based), so `hidden_count` is the real signal for probing.
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
| glassbox-overview | Glass Box: LLM observability | cost, tokens, guardrail verdicts, latency |
| glassbox-quality | Glass Box: Conversation quality | answered rate, top unanswered prompts, sentiment, language mismatch, topics, off topic rate, faithfulness, relevance, flagged reasons |
| glassbox-owasp | Glass Box: OWASP LLM Top 10 coverage | live evidence per risk (LLM01, 02, 05, 07, 08, 09, 10), model usage for LLM03 and LLM06 (visibility only), risk to control table |
