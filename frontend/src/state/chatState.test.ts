import { initialState, lastUserQuestion, newId, pendingCount, reducer, userMessageFor, type AssistantMsg } from "./chatState";
import type { ChatResponse } from "../lib/types";

const resp = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "18 days [pto-policy]", blocked: false, block_reason: [], trace_id: "abc", persona: "employee", model: "gpt-5.4-mini",
  engine: "sdk", docs: [], hidden: [], usage: { input_tokens: 10, output_tokens: 5, thinking_tokens: 0 }, cost_usd: 0.001,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 4, injection_score: 0 }, stages: [], ...over,
});

const start = () => initialState("employee", "eis-gpt-mini");
const sendAction = (text: string) => ({ type: "send" as const, text, userId: newId(), assistantId: newId() });

test("send adds the user message and a pending assistant bound to the current persona, model and engine", () => {
  let s = reducer(start(), { type: "setEngine", engine: "langchain" });
  s = reducer(s, sendAction("How many PTO days?"));
  const [u, a] = s.messages as [any, AssistantMsg];
  expect(u).toMatchObject({ kind: "user", text: "How many PTO days?", persona: "employee" });
  expect(a).toMatchObject({ kind: "assistant", status: "pending", replyTo: u.id, persona: "employee", model: "eis-gpt-mini", engine: "langchain" });
  expect(s.selectedId).toBe(a.id);
  expect(pendingCount(s)).toBe(1);
});

test("receive completes the right message and accumulates spend", () => {
  let s = reducer(start(), sendAction("q1"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "receive", id, response: resp({ cost_usd: 0.002 }) });
  expect((s.messages[1] as AssistantMsg).status).toBe("done");
  expect(s.spendUsd).toBeCloseTo(0.002);
  expect(pendingCount(s)).toBe(0);
});

test("a persona switch while a request is pending does not change that pending message", () => {
  let s = reducer(start(), sendAction("Show salary bands"));
  const pendingId = s.messages[1].id;
  s = reducer(s, { type: "setPersona", persona: "exec", label: "Rachel Tan, Chief People Officer" });
  expect(s.persona).toBe("exec");
  s = reducer(s, { type: "receive", id: pendingId, response: resp({ persona: "employee" }) });
  const a = s.messages.find((m) => m.id === pendingId) as AssistantMsg;
  expect(a.persona).toBe("employee");
  expect(a.response?.persona).toBe("employee");
});

test("switching persona inserts one divider only when the conversation has messages", () => {
  const empty = reducer(start(), { type: "setPersona", persona: "hr", label: "Priya Nair, HR Business Partner" });
  expect(empty.messages).toEqual([]);
  let s = reducer(start(), sendAction("hi"));
  s = reducer(s, { type: "setPersona", persona: "hr", label: "Priya Nair, HR Business Partner" });
  expect(s.messages[s.messages.length - 1]).toMatchObject({ kind: "divider", text: "Now asking as Priya Nair, HR Business Partner" });
  const same = reducer(s, { type: "setPersona", persona: "hr", label: "x" });
  expect(same.messages.length).toBe(s.messages.length);
});

test("fail marks the message as an error and retry re-opens it as pending", () => {
  let s = reducer(start(), sendAction("q"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "fail", id, error: { status: 503, code: "gemma_offline", hint: "start it" } });
  expect(s.messages[1]).toMatchObject({ status: "error", error: { code: "gemma_offline" } });
  s = reducer(s, { type: "retry", id });
  expect(s.messages[1]).toMatchObject({ status: "pending" });
  expect((s.messages[1] as AssistantMsg).error).toBeUndefined();
});

test("userMessageFor and lastUserQuestion find the question behind an answer", () => {
  let s = reducer(start(), sendAction("first"));
  s = reducer(s, sendAction("second"));
  expect(lastUserQuestion(s)?.text).toBe("second");
  const firstAssistant = s.messages.find((m) => m.kind === "assistant") as AssistantMsg;
  expect(userMessageFor(s, firstAssistant.id)?.text).toBe("first");
});

test("select, reset and unknown ids are safe", () => {
  let s = reducer(start(), sendAction("q"));
  expect(reducer(s, { type: "receive", id: "nope", response: resp() })).toEqual(s);
  expect(reducer(s, { type: "fail", id: "nope", error: { status: 500, code: "x" } })).toEqual(s);
  s = reducer(s, { type: "select", id: null });
  expect(s.selectedId).toBeNull();
  s = reducer(s, { type: "reset" });
  expect(s).toMatchObject({ messages: [], spendUsd: 0, selectedId: null, persona: "employee", model: "eis-gpt-mini" });
});

test("receive/fail/retry for unknown ids return the same state, add no spend and never throw", () => {
  const s = reducer(start(), sendAction("q"));
  expect(() => reducer(s, { type: "receive", id: "nope", response: resp({ cost_usd: 5 }) })).not.toThrow();
  const r = reducer(s, { type: "receive", id: "nope", response: resp({ cost_usd: 5 }) });
  expect(r).toBe(s);
  expect(r.spendUsd).toBe(0);
  expect(reducer(s, { type: "fail", id: "nope", error: { status: 500, code: "x" } })).toBe(s);
  expect(reducer(s, { type: "retry", id: "nope" })).toBe(s);
});

test("receive selects the answered message even when the user is inspecting another one", () => {
  let s = reducer(start(), sendAction("first"));
  const firstId = s.messages[1].id;
  s = reducer(s, sendAction("second"));
  const secondId = s.messages[3].id;
  s = reducer(s, { type: "select", id: firstId });
  expect(s.selectedId).toBe(firstId);
  s = reducer(s, { type: "receive", id: secondId, response: resp() });
  expect(s.selectedId).toBe(secondId);
  expect(pendingCount(s)).toBe(1); // the first message is still pending
});

test("retry on a done message is a no-op and spend is unchanged", () => {
  let s = reducer(start(), sendAction("q"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "receive", id, response: resp({ cost_usd: 0.002 }) });
  const r = reducer(s, { type: "retry", id });
  expect(r).toBe(s);
  expect(r.spendUsd).toBeCloseTo(0.002);
});

test("a duplicate receive for an already-done message does not add spend again", () => {
  let s = reducer(start(), sendAction("q"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "receive", id, response: resp({ cost_usd: 0.002 }) });
  s = reducer(s, { type: "select", id: null });
  const r = reducer(s, { type: "receive", id, response: resp({ cost_usd: 0.002 }) });
  expect(r).toBe(s);
  expect(r.spendUsd).toBeCloseTo(0.002);
  expect(r.selectedId).toBeNull();
});

test("fail on an already-done message leaves it done", () => {
  let s = reducer(start(), sendAction("q"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "receive", id, response: resp() });
  const r = reducer(s, { type: "fail", id, error: { status: 500, code: "x" } });
  expect(r).toBe(s);
  expect((r.messages[1] as AssistantMsg).status).toBe("done");
});

test("retry on an error message re-opens it and the following receive adds cost exactly once", () => {
  let s = reducer(start(), sendAction("q"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "fail", id, error: { status: 503, code: "gemma_offline" } });
  expect(s.spendUsd).toBe(0);
  s = reducer(s, { type: "retry", id });
  expect(s.messages[1]).toMatchObject({ status: "pending" });
  expect((s.messages[1] as AssistantMsg).response).toBeUndefined();
  expect(s.spendUsd).toBe(0);
  s = reducer(s, { type: "receive", id, response: resp({ cost_usd: 0.003 }) });
  expect(s.spendUsd).toBeCloseTo(0.003);
  s = reducer(s, { type: "receive", id, response: resp({ cost_usd: 0.003 }) });
  expect(s.spendUsd).toBeCloseTo(0.003);
});

test("arrowing through personas keeps one divider that names the latest persona", () => {
  let s = reducer(start(), sendAction("hi"));
  s = reducer(s, { type: "setPersona", persona: "hr", label: "B" });
  s = reducer(s, { type: "setPersona", persona: "exec", label: "C" });
  const dividers = s.messages.filter((m) => m.kind === "divider");
  expect(dividers).toHaveLength(1);
  expect(dividers[0]).toMatchObject({ text: "Now asking as C" });
});

test("switching back to the persona before the divider removes the divider", () => {
  let s = reducer(start(), sendAction("hi"));
  s = reducer(s, { type: "setPersona", persona: "hr", label: "B" });
  s = reducer(s, { type: "setPersona", persona: "employee", label: "A" });
  expect(s.messages.filter((m) => m.kind === "divider")).toHaveLength(0);
  expect(s.persona).toBe("employee");
});

test("switching A to B to C to A leaves no divider", () => {
  let s = reducer(start(), sendAction("hi"));
  for (const [p, l] of [["hr", "B"], ["exec", "C"], ["employee", "A"]]) s = reducer(s, { type: "setPersona", persona: p, label: l });
  expect(s.messages.filter((m) => m.kind === "divider")).toHaveLength(0);
});

test("retry can rebind the message to another model while keeping persona and engine", () => {
  let s = reducer(start(), { type: "setModel", model: "gemma" });
  s = reducer(s, { type: "setEngine", engine: "langchain" });
  s = reducer(s, sendAction("q"));
  const id = s.messages[1].id;
  s = reducer(s, { type: "fail", id, error: { status: 503, code: "gemma_offline" } });
  s = reducer(s, { type: "retry", id, model: "eis-gpt-mini" });
  expect(s.messages[1]).toMatchObject({ status: "pending", model: "eis-gpt-mini", persona: "employee", engine: "langchain" });
});

test("retry with a model override still only works from the error state", () => {
  let s = reducer(start(), sendAction("q"));
  const id = s.messages[1].id;
  const after = reducer(s, { type: "retry", id, model: "gemma" });
  expect(after).toBe(s);
  s = reducer(s, { type: "receive", id, response: resp() });
  expect(reducer(s, { type: "retry", id, model: "gemma" })).toBe(s);
});
