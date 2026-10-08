# Glass Box demo script (10 minutes)

Story: an HR assistant for a company called Foo Corp. The same question gets different answers for different people, and every step is visible, traceable and costed.

People in the app: Maya Lim (Software Engineer, role employee) and Daniel Ong (Engineering Manager, role manager). Maya reads 6 of the 20 documents and Daniel reads 11. The documents only HR or executives can read are hidden from both of them.

## Before you start (5 minutes ahead)

1. Run `deploy/scripts/demo_up.sh` (add `--gemma` at least 10 minutes ahead if you will show Gemma).
2. Open https://107-178-251-254.sslip.io and enter the password from `backend/secrets/app_password.txt`. Do not show the file on screen.
3. Open Kibana in a second tab: APM service `glassbox-backend`, the dashboard `Glass Box: LLM observability`, and the Security alerts page.
4. Pick GPT-5.4 mini as the model and Direct SDK as the engine.
5. Provider usage: EIS token usage is under Billing and subscription, Usage, Inference in Elastic Cloud (it lags real traffic).

## Step 1: Same question, different person (2 minutes) - pillar: access control (DLS)

| Do | Say | Expect |
|---|---|---|
| Select Maya Lim in the rail. Type `What are the salary bands for L3 to L5?` and send. | "Maya is a software engineer. She asks about pay bands, which only managers can read." | An answer saying the documents do not contain it. No citation. |
| Click Inspect on the answer to open the LLM Observability drawer. Scroll to "Hidden by DLS". | "The search ran as Maya. Elasticsearch itself removed the restricted document before the model ever saw it. Here is the ghost card of what she cannot see." | A ghost card for `salary-bands` (Salary Bands L3 to L5, Confidential) with a lock icon. The restricted HR and executive documents show as ghost cards too. |
| Close the drawer. Select Daniel Ong in the rail, then click "Ask again as Daniel Ong" under the answer. | "Same question, same model, now as the Engineering Manager." | A real answer with the L3, L4 and L5 bands that cites `[salary-bands]`. |
| Inspect again. | "Daniel's document list includes the salary bands. The HR and executive documents are still hidden from him." | `salary-bands` in the document list, and fewer ghost cards than for Maya. |

Key point: the control is document level security in the data layer, not a prompt instruction.

## Step 2: Follow one request end to end (3 minutes) - pillar: tracing

| Do | Say | Expect |
|---|---|---|
| In the LLM Observability drawer click "Open trace in Kibana". | "Every answer links to its trace." | Kibana APM opens a new tab on the trace. |
| Walk the waterfall from the top. | "The request enters the API, then the guardrail check, then hybrid search in Elasticsearch, then prompt build, then the LLM call through the Elastic Inference Service." | Spans `POST /api/chat`, `guardrail.check`, `retrieval.hybrid`, `prompt.build`, `chat gpt-5.4-mini`. |
| Click the `chat` span and open its attributes. | "Prompt and response are captured on the span, plus token counts and the cost." | `gen_ai.input.messages`, `gen_ai.output.messages`, token counts, and `app.genai.cost_usd` on the root span. |
| Back in the app switch the engine to LangChain and ask `How many PTO days do I get?` as Maya. Open its trace. | "Same product, a different framework. The instrumentation still shows each step nested under the chain." | Stages `guardrail.check`, `retrieval.hybrid`, `llm.generate`, plus an `invoke_workflow RunnableSequence` span. The trace arrives about 1 minute after the request. |

## Step 3: OWASP and quality (3 minutes) - pillar: guardrails, security and quality

Open the Red team menu (sections Security and Quality; the texts are in `frontend/src/lib/prompts.ts`). Input checks run before the model; output and quality checks run after the answer, asynchronously (about 5 to 10 seconds). After each answered prompt open "Output guardrail and quality" in the LLM Observability panel and read "What Elastic checks on this answer" (one row per check with what Elastic does and in which pipeline step; the OWASP id opens the official OWASP page and "See it in Kibana" opens the matching dashboard), then use "Open the response log" (Discover, `logs-genai_response*` by trace id) or "Try it in Dev Tools" (simulates the `genai-quality` pipeline on that answer). Both need a Kibana login.

| Do | Say | Expect |
|---|---|---|
| Red team, Should be blocked: "Ignore previous instructions". | "A prompt injection attempt. A trained classifier catches it before any model is called." | Blocked, reason `prompt_injection`, no model cost, no quality section. |
| Red team, Should be blocked: "Email address". Then Flagged only: "Salary figure". | "Personal data in the prompt is blocked, some prompts are only flagged for review." | Blocked with `pii_email`. Salary answered and flagged `pii_salary`. Security Alerts, rule `glassbox-flagged-prompts`, shows them after about 1 minute. |
| Red team, Should be blocked: "System prompt extraction" (LLM07). | "Asking the model to repeat its instructions is stopped before any model call by the Elastic hosted injection model. That is the prevention." | Blocked, reason `prompt_injection`, no response log. |
| LLM07 output detection: open an answered response's "Try it in Dev Tools", edit the `genai.response_text` in the simulate body so it says `My internal reference id is` followed by the system prompt id (paste the id yourself; it is never stored in this repo or shown in the UI). | "If a leak ever got past the input check, the answer itself is matched against a canary and the Security rule fires." | The simulate result has `output_verdict` FLAGGED and `output_reasons` containing `system_prompt_leak`. Run it against the project whose pipeline carries the canary. |
| Red team, Output risks: "Markup in the answer" (LLM05). | "Answers that carry script tags or links are flagged before anything renders them." | A markup finding on the response log for the script tag and link. |
| Red team, Output risks: "PII echo" (LLM02). | "Personal data in the answer is checked, not only in the prompt." | A PII finding on the response log if the answer repeats an email address or phone number. |
| Red team, Quality: "Hallucination bait" (LLM09). | "An LLM judge checks whether the answer is grounded in the cited documents." | A judge verdict on the response log, ungrounded if the answer invents a clause number. |
| Red team, Quality: "Off topic" (laksa), then "Non English user (answered in French)". | "Topic and language are scored on every answer. A French question answered in French is correctly not a problem." | Laksa: `quality.off_topic` true (the judge's `on_topic` verdict). French: answered in French, `quality.lang_mismatch` false, `quality.on_topic` true. |
| Language mismatch demo: open any English answer's "Try it in Dev Tools" and edit `genai.response_text` to a French or Spanish sentence of 30 or more characters. | "If the assistant ever answers in a different language than the question, this flags it." | `quality.lang_mismatch` true. |
| Red team, Quality: "Rude and negative", then "Positive feedback". | "User sentiment is read by the LLM judge on three classes; the eland model's binary label is kept as the raw signal." | `quality.user_sentiment` negative, then positive. `quality.sentiment_label` is the raw binary signal (neutral prompts read NEGATIVE), so alerts use `user_sentiment`. |
| Red team, Quality: "Unanswerable" (CEO's favourite colour). | "Failures to answer are tracked too." | `quality.answered` is false. |
| Click "Conversation quality dashboard", then "OWASP coverage dashboard". | "Every answer rolls up here: sentiment, language, topic, answered, and each OWASP risk." | Dashboards `glassbox-quality` and `glassbox-owasp`. Allow a minute for the latest answers to appear. |

Exact findings depend on the live model answers, so treat the Expect column as what to look for.

After the table, show where the prompt itself lives (blocked requests have no LLM span, so no `gen_ai.input.messages`):

- Trace: the `guardrail.check` span carries the prompt in the attribute `guardrail.prompt_text` (set when `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` is `SPAN_ONLY`, `SPAN_AND_EVENT` or `true`; truncated to 4096 characters).
- Log: the correlated log record in the Observability project, data stream `logs-genai_guardrail.otel-default`, has the same `trace_id`, the prompt in `attributes.genai.prompt_text` and the verdict in `attributes.security.threat_verdict`, set by the `genai-guardrail` ingest pipeline.
- Dev Tools: in the Guardrail section click "Try it in Dev Tools" (clean or flagged). Kibana Console opens prefilled with this prompt run against the injection model, the entity model and the `genai-guardrail` pipeline simulate. It needs a Kibana login.

## Step 4: Cost (2 minutes) - pillar: cost control

| Do | Say | Expect |
|---|---|---|
| Point at "Session cost" in the app header after a few chats. | "The app shows what this session has cost, in dollars." | A small figure, a fraction of a cent per answer. |
| Kibana, dashboard `Glass Box: LLM observability`. | "Spend over time by model, tokens, average cost per person, guardrail verdicts and stage latency, all from the same traces." | Eight panels with data. Average cost is a fraction of a cent per request. |
| Open Kibana, Observability, APM, Services, `glassbox-backend`, and the Kubernetes dashboards linked from it. | "Out of the box views: the GenAI service view for the model calls, and Kubernetes infrastructure for the pods." | Latency, throughput, token usage per model, and pod CPU and memory. |
| In Elastic Cloud open Billing and subscription, Usage, Inference. | "The model calls run on the Elastic Inference Service, so the token usage is billed and visible per model in Elastic." | EIS token usage; it can lag real traffic. |
| Show the alert firing. In a terminal run `source backend/.venv/bin/activate && python -m elastic.apply --project observability --cost-threshold 0.0001`, send two chats, then open Observability, Rules, `Glass Box: LLM spend above threshold`. | "The budget rule watches hourly spend. I lowered the limit to nearly nothing to trigger it live." | An active alert within about a minute. |
| Restore the real threshold: `python -m elastic.apply --project observability --cost-threshold 0.25` | "Back to the real limit of 25 cents per hour." | Rule back at 0.25. Do this before you leave the demo. |

## Step 5: Self-hosted model (1 minute) - pillar: model choice (needs `demo_up.sh --gemma`)

| Do | Say | Expect |
|---|---|---|
| Before starting: show the model list with Gemma greyed out and marked Offline. Then (already started ahead of the demo) refresh the list. | "Gemma runs on our own GPU. It is off by default because it costs about $5 to $6 an hour." | Gemma shows Offline when the VM is stopped, selectable when it is serving. |
| Select Gemma, ask `What is the remote work policy?` | "Same app, same guardrails, same traces, different model, and cost is estimated from GPU time." | An answer in a few seconds. The trace span is named `chat google/gemma-4-31B-it`. Optional: open the `Glass Box: Gemma (vLLM)` dashboard for token and queue metrics (data exists only while the VM runs). |
| Afterwards run `deploy/scripts/demo_down.sh`. | "One command stops the GPU and the traffic generator." | Output ends with "traffic generator suspended, gemma TERMINATED". |

If Gemma is not running and someone selects it, the app shows an inline error with a "Try with GPT-5.4 mini" button.

## After the demo

Run `deploy/scripts/demo_down.sh` (add `--teardown` to remove the load balancer too). Confirm the threshold was restored to 0.25.

## LLM Observability deep links

- Flagged or blocked prompt: in the Guardrail section click "See where it was blocked" (APM trace, span `guardrail.check`) and "View detection in Elastic Security" (Alerts filtered to rule `glassbox-flagged-prompts`). The alert can take a few minutes to appear.
- Retrieval: click a document title to open it in Kibana Discover (Kibana login needed; your Kibana role applies, not the persona). Hidden cards have no link.
- Model and cost: "Open cost dashboard" opens `Glass Box: LLM observability`.
