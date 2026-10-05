import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssistantMessage } from "./AssistantMessage";
import type { AssistantMsg } from "../state/chatState";
import type { ChatResponse } from "../lib/types";

const response = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "You get 18 days [pto-policy].", blocked: false, block_reason: [], trace_id: "t1", persona: "employee", model: "gpt-5.4-mini", engine: "sdk",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.1 }], hidden: [],
  usage: { input_tokens: 1200, output_tokens: 80, thinking_tokens: 0 }, cost_usd: 0.00042,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 40, injection_score: 0.01 },
  stages: [{ name: "guardrail.check", ms: 40 }, { name: "llm.generate", ms: 800 }], ...over,
});
const msg = (over: Partial<AssistantMsg> = {}): AssistantMsg => ({
  id: "a1", kind: "assistant", replyTo: "u1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: "done", response: response(), ...over,
});
const models = [
  { key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis" as const, model_id: "g1", available: true },
  { key: "gemma", label: "Gemma 4 31B (self-hosted)", provider: "gemma" as const, model_id: "gm", available: false },
];
const base = { models, selected: false, onSelect: vi.fn(), onCitation: vi.fn(), onRetry: vi.fn(), personaName: "Maya Lim" };

test("a done answer shows text, a meta row and an Inspect control", async () => {
  const onSelect = vi.fn();
  render(<AssistantMessage {...base} onSelect={onSelect} msg={msg()} />);
  expect(screen.getByText(/you get 18 days/i)).toBeInTheDocument();
  expect(screen.getByText(/1 source/i)).toBeInTheDocument();
  expect(screen.getByText("$0.00042")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /inspect/i }));
  expect(onSelect).toHaveBeenCalledWith("a1");
});

test("pending shows a busy skeleton instead of empty space", () => {
  render(<AssistantMessage {...base} msg={msg({ status: "pending", response: undefined })} />);
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
});

test("a blocked prompt shows the block card with human reasons and no answer text", () => {
  const blocked = response({ blocked: true, answer: "", block_reason: ["prompt_injection", "pii_email"], guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection", "pii_email"], status: "ok", latency_ms: 30, injection_score: 0.99 }, docs: [], cost_usd: 0 });
  render(<AssistantMessage {...base} msg={msg({ response: blocked })} />);
  expect(screen.getByRole("heading", { name: /blocked by the guardrail/i })).toBeInTheDocument();
  expect(screen.getByText("Prompt injection attempt")).toBeInTheDocument();
  expect(screen.getByText("Email address")).toBeInTheDocument();
});

test("a flagged but allowed answer shows the answer and a flag note", () => {
  const flagged = response({ guardrail: { verdict: "FLAGGED", reasons: ["pii_salary"], status: "ok", latency_ms: 30, injection_score: 0.02 } });
  render(<AssistantMessage {...base} msg={msg({ response: flagged })} />);
  expect(screen.getByText(/you get 18 days/i)).toBeInTheDocument();
  expect(screen.getByText(/flagged for review/i)).toBeInTheDocument();
  expect(screen.getByText("Salary figure")).toBeInTheDocument();
});

test("a degraded guardrail is called out in words", () => {
  const degraded = response({ guardrail: { verdict: "CLEAN", reasons: [], status: "degraded", latency_ms: 1500, injection_score: null } });
  render(<AssistantMessage {...base} msg={msg({ response: degraded })} />);
  expect(screen.getByText(/guardrail models were slow or unavailable/i)).toBeInTheDocument();
});

test("gemma offline and upstream errors show a recoverable error with retry", async () => {
  const onRetry = vi.fn();
  const { rerender } = render(<AssistantMessage {...base} onRetry={onRetry} msg={msg({ status: "error", response: undefined, error: { status: 503, code: "gemma_offline", hint: "start the VM" } })} />);
  expect(screen.getByText(/gemma model is offline/i)).toBeInTheDocument();
  expect(screen.getByText(/start the vm/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /try again/i }));
  expect(onRetry).toHaveBeenCalledWith("a1");
  rerender(<AssistantMessage {...base} onRetry={onRetry} msg={msg({ status: "error", response: undefined, error: { status: 502, code: "upstream_error" } })} />);
  expect(screen.getByText(/model service had a problem/i)).toBeInTheDocument();
});

test("an empty answer string is shown as a neutral message, not blank", () => {
  render(<AssistantMessage {...base} msg={msg({ response: response({ answer: "" }) })} />);
  expect(screen.getByText(/no answer was returned/i)).toBeInTheDocument();
});

test("citations in a done answer only chip documents that were retrieved", () => {
  render(<AssistantMessage {...base} msg={msg({ response: response({ answer: "See [pto-policy] and [ghost]." }) })} />);
  expect(screen.getByRole("button", { name: "pto-policy" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "ghost" })).toBeNull();
  expect(screen.getByText(/\[ghost\]/)).toBeInTheDocument();
});

test("an error status with no error object still shows a generic recoverable error", async () => {
  const onRetry = vi.fn();
  render(<AssistantMessage {...base} onRetry={onRetry} msg={msg({ status: "error", response: undefined })} />);
  expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /try again/i }));
  expect(onRetry).toHaveBeenCalledWith("a1");
});

test("skeleton pulse is switched off under prefers-reduced-motion", () => {
  render(<AssistantMessage {...base} msg={msg({ status: "pending", response: undefined })} />);
  const bars = screen.getByRole("status").querySelectorAll("div");
  expect(bars.length).toBe(3);
  bars.forEach((b) => expect(b.className).toContain("motion-reduce:animate-none"));
});

test("a timed out request shows the timeout copy", () => {
  render(<AssistantMessage {...base} msg={msg({ status: "error", error: { status: 0, code: "timeout" } })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("The request took too long. Try again.");
});

test("when the failed message's model is offline the card offers the first available model instead of retrying it", async () => {
  const onRetry = vi.fn();
  render(<AssistantMessage {...base} onRetry={onRetry} msg={msg({ model: "gemma", status: "error", response: undefined, error: { status: 503, code: "gemma_offline" } })} />);
  expect(screen.queryByRole("button", { name: /^try again$/i })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Try with GPT-5.4 mini" }));
  expect(onRetry).toHaveBeenCalledWith("a1", "eis-gpt-mini");
});

test("when the failed message's model is available the plain Try again is shown", async () => {
  const onRetry = vi.fn();
  render(<AssistantMessage {...base} onRetry={onRetry} msg={msg({ model: "eis-gpt-mini", status: "error", response: undefined, error: { status: 502, code: "upstream_error" } })} />);
  expect(screen.queryByRole("button", { name: /try with/i })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: /^try again$/i }));
  expect(onRetry).toHaveBeenCalledWith("a1");
});

test("when no model is available the plain Try again is shown", () => {
  render(<AssistantMessage {...base} models={models.map((m) => ({ ...m, available: false }))} msg={msg({ model: "gemma", status: "error", response: undefined, error: { status: 503, code: "gemma_offline" } })} />);
  expect(screen.getByRole("button", { name: /^try again$/i })).toBeInTheDocument();
});

test("a rate limited request shows the rate limit copy", () => {
  render(<AssistantMessage {...base} msg={msg({ status: "error", response: undefined, error: { status: 429, code: "rate_limited" } })} />);
  expect(screen.getByText("Too many requests. Wait a moment and try again.")).toBeInTheDocument();
});
