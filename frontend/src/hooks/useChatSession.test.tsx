import { act, renderHook } from "@testing-library/react";
import { useChatSession } from "./useChatSession";
import * as apiMod from "../lib/api";
import { ApiError } from "../lib/api";
import type { ChatResponse, ModelInfo, Persona } from "../lib/types";

const personas: Persona[] = [
  { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 },
  { id: "manager", name: "Daniel Ong", title: "Engineering Manager", can_read_docs: 11, total_docs: 20 },
];
const models: ModelInfo[] = [
  { key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis", model_id: "g1", available: true },
  { key: "gemma", label: "Gemma", provider: "gemma", model_id: "gm", available: true },
];
const ok = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "a [pto-policy]", blocked: false, block_reason: [], trace_id: "t", persona: "employee", model: "g1", engine: "sdk", docs: [], hidden: [],
  usage: { input_tokens: 1, output_tokens: 1, thinking_tokens: 0 }, cost_usd: 0.001,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 1, injection_score: 0 }, stages: [], ...over,
});

function setup(m = models) {
  const refresh = vi.fn();
  return renderHook(() => useChatSession(personas, m, refresh));
}

test("send posts with the persona, model and engine at send time, then stores the answer and clears the draft", async () => {
  const chat = vi.spyOn(apiMod.api, "chat").mockResolvedValue(ok());
  const { result } = setup();
  act(() => result.current.setDraft("How many PTO days?"));
  await act(async () => { await result.current.send("How many PTO days?"); });
  expect(chat).toHaveBeenCalledWith({ message: "How many PTO days?", persona: "employee", model: "eis-gpt-mini", engine: "sdk" });
  expect(result.current.draft).toBe("");
  expect(result.current.state.spendUsd).toBeCloseTo(0.001);
  expect(result.current.current?.status).toBe("done");
});

test("a second send while one is pending is ignored", async () => {
  let resolve!: (r: ChatResponse) => void;
  const chat = vi.spyOn(apiMod.api, "chat").mockReturnValue(new Promise((r) => { resolve = r; }));
  const { result } = setup();
  act(() => { void result.current.send("one"); });
  act(() => { void result.current.send("two"); });
  expect(chat).toHaveBeenCalledTimes(1);
  await act(async () => { resolve(ok()); });
});

test("an empty send is ignored", async () => {
  const chat = vi.spyOn(apiMod.api, "chat").mockResolvedValue(ok());
  const { result } = setup();
  await act(async () => { await result.current.send("   "); });
  expect(chat).not.toHaveBeenCalled();
});

test("switching persona while pending attaches the answer to the original persona", async () => {
  let resolve!: (r: ChatResponse) => void;
  vi.spyOn(apiMod.api, "chat").mockReturnValue(new Promise((r) => { resolve = r; }));
  const { result } = setup();
  act(() => { void result.current.send("q"); });
  act(() => result.current.dispatch({ type: "setPersona", persona: "manager", label: "Daniel Ong, Engineering Manager" }));
  await act(async () => { resolve(ok()); });
  const a = result.current.state.messages.find((m) => m.kind === "assistant") as any;
  expect(a.persona).toBe("employee");
  expect(a.status).toBe("done");
  expect(result.current.state.persona).toBe("manager");
});

test("failure keeps the draft intact for 401 and marks the message as an error", async () => {
  vi.spyOn(apiMod.api, "chat").mockRejectedValue(new ApiError(401, "unauthorized"));
  const { result } = setup();
  act(() => result.current.setDraft("keep me"));
  await act(async () => { await result.current.send("keep me"); });
  expect(result.current.draft).toBe("keep me");
  expect((result.current.state.messages[1] as any).status).toBe("error");
});

test("retry re-sends the original question with the original persona", async () => {
  const chat = vi.spyOn(apiMod.api, "chat").mockRejectedValueOnce(new ApiError(503, "gemma_offline")).mockResolvedValue(ok());
  const { result } = setup();
  await act(async () => { await result.current.send("hello"); });
  act(() => result.current.dispatch({ type: "setPersona", persona: "manager", label: "x" }));
  const id = (result.current.state.messages.find((m) => m.kind === "assistant") as any).id;
  await act(async () => { await result.current.retry(id); });
  expect(chat).toHaveBeenLastCalledWith({ message: "hello", persona: "employee", model: "eis-gpt-mini", engine: "sdk" });
  expect((result.current.state.messages.find((m) => m.kind === "assistant") as any).status).toBe("done");
});

test("retry with a model override sends that model and rebinds the message", async () => {
  const chat = vi.spyOn(apiMod.api, "chat").mockRejectedValueOnce(new ApiError(503, "gemma_offline")).mockResolvedValue(ok());
  const { result } = setup();
  act(() => result.current.dispatch({ type: "setModel", model: "gemma" }));
  await act(async () => { await result.current.send("hello"); });
  const id = (result.current.state.messages.find((m) => m.kind === "assistant") as any).id;
  await act(async () => { await result.current.retry(id, "eis-gpt-mini"); });
  expect(chat).toHaveBeenLastCalledWith({ message: "hello", persona: "employee", model: "eis-gpt-mini", engine: "sdk" });
  const a = result.current.state.messages.find((m) => m.kind === "assistant") as any;
  expect(a).toMatchObject({ status: "done", model: "eis-gpt-mini" });
});

test("selecting a citation selects that message and highlights the doc briefly", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(ok());
  const { result } = setup();
  await act(async () => { await result.current.send("q"); });
  const id = (result.current.state.messages.find((m) => m.kind === "assistant") as any).id;
  vi.useFakeTimers();
  try {
    act(() => result.current.selectCitation("pto-policy", id));
    expect(result.current.highlightDocId).toBe("pto-policy");
    act(() => { vi.advanceTimersByTime(2600); });
    expect(result.current.highlightDocId).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});

test("when the selected model becomes unavailable the hook falls back to an available one", () => {
  const refresh = vi.fn();
  const { result, rerender } = renderHook(({ m }) => useChatSession(personas, m, refresh), { initialProps: { m: models } });
  act(() => result.current.dispatch({ type: "setModel", model: "gemma" }));
  rerender({ m: [models[0], { ...models[1], available: false }] });
  expect(result.current.state.model).toBe("eis-gpt-mini");
});

test("refreshModels is polled every 15 s while Gemma is unavailable", () => {
  vi.useFakeTimers();
  try {
    const refresh = vi.fn();
    renderHook(() => useChatSession(personas, [models[0], { ...models[1], available: false }], refresh));
    act(() => { vi.advanceTimersByTime(15000); });
    expect(refresh).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("an external draft control is used instead of the internal draft", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(ok());
  const set = vi.fn();
  const { result } = renderHook(() => useChatSession(personas, models, vi.fn(), ["typed", set] as const));
  expect(result.current.draft).toBe("typed");
  await act(async () => { await result.current.send("typed"); });
  expect(set).toHaveBeenCalledWith("");
});

test("a gemma_offline failure refreshes the model list immediately", async () => {
  vi.spyOn(apiMod.api, "chat").mockRejectedValue(new ApiError(503, "gemma_offline"));
  const refresh = vi.fn();
  const { result } = renderHook(() => useChatSession(personas, models, refresh));
  await act(async () => { await result.current.send("hi"); });
  expect(refresh).toHaveBeenCalledTimes(1);
});

test("other failures do not trigger a model refresh", async () => {
  vi.spyOn(apiMod.api, "chat").mockRejectedValue(new ApiError(502, "upstream_error"));
  const refresh = vi.fn();
  const { result } = renderHook(() => useChatSession(personas, models, refresh));
  await act(async () => { await result.current.send("hi"); });
  expect(refresh).not.toHaveBeenCalled();
});

test("personas arriving after mount select the first persona", () => {
  const { result, rerender } = renderHook(({ p }) => useChatSession(p, models, vi.fn()), { initialProps: { p: [] as Persona[] } });
  expect(result.current.state.persona).toBe("");
  rerender({ p: personas });
  expect(result.current.state.persona).toBe("employee");
});

test("selectedId follows the pending assistant message right after send", async () => {
  let resolve!: (r: ChatResponse) => void;
  vi.spyOn(apiMod.api, "chat").mockReturnValue(new Promise((r) => { resolve = r; }));
  const { result } = setup();
  act(() => { void result.current.send("q"); });
  const a = result.current.state.messages.find((m) => m.kind === "assistant") as any;
  expect(a.status).toBe("pending");
  expect(result.current.state.selectedId).toBe(a.id);
  await act(async () => { resolve(ok()); });
});

test("reset clears the draft held by the session", () => {
  const { result } = setup();
  act(() => result.current.setDraft("x"));
  act(() => { result.current.dispatch({ type: "reset" }); result.current.setDraft(""); });
  expect(result.current.draft).toBe("");
  expect(result.current.state.messages).toEqual([]);
});
