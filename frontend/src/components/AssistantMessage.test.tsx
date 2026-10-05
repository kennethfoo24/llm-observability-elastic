import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssistantMessage } from "./AssistantMessage";
import type { AssistantMsg } from "../state/chatState";
import type { ChatResponse } from "../lib/types";

const response = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "You get 18 days [pto-policy].", blocked: false, block_reason: [], trace_id: "t1", persona: "employee", model: "gemini-3.1-flash-lite", engine: "sdk",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.1 }], hidden: [],
  usage: { input_tokens: 1200, output_tokens: 80, thinking_tokens: 0 }, cost_usd: 0.00042,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 40, injection_score: 0.01 },
  stages: [{ name: "guardrail.check", ms: 40 }, { name: "llm.generate", ms: 800 }], ...over,
});
const msg = (over: Partial<AssistantMsg> = {}): AssistantMsg => ({
  id: "a1", kind: "assistant", replyTo: "u1", persona: "employee", model: "flash-lite", engine: "sdk", status: "done", response: response(), ...over,
});
const base = { selected: false, onSelect: vi.fn(), onCitation: vi.fn(), onRetry: vi.fn(), personaName: "Maya Lim" };

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
