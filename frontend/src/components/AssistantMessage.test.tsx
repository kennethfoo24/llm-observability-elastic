import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import userEvent from "@testing-library/user-event";
import { AssistantMessage } from "./AssistantMessage";
import type { AssistantMsg } from "../state/chatState";
import type { ChatResponse, Persona } from "../lib/types";

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
const maya: Persona = { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 };
const daniel: Persona = { id: "manager", name: "Daniel Ong", title: "Engineering Manager", can_read_docs: 11, total_docs: 20 };
const base = {
  models, selected: false, onSelect: vi.fn(), onCitation: vi.fn(), onRetry: vi.fn(), personaName: "Maya Lim", persona: maya, otherPersona: daniel,
  kibanaUrl: "https://kb.example", pending: false, onAskAgain: vi.fn(), onRegenerate: vi.fn(), onOpenDetails: vi.fn(),
};

test("a done answer shows the text, a guardrail chip, the source count, and no old meta row or Inspect button", () => {
  render(<AssistantMessage {...base} msg={msg()} />);
  expect(screen.getByText(/you get 18 days/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /guardrail passed/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /1 source/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /inspect/i })).toBeNull();
  expect(screen.queryByText("$0.00042")).toBeNull();
});

test("clicking a status chip selects the answer and opens the details", async () => {
  const onSelect = vi.fn();
  const onOpenDetails = vi.fn();
  render(<AssistantMessage {...base} onSelect={onSelect} onOpenDetails={onOpenDetails} msg={msg()} />);
  await userEvent.click(screen.getByRole("button", { name: /guardrail passed/i }));
  expect(onSelect).toHaveBeenCalledWith("a1");
  expect(onOpenDetails).toHaveBeenCalledWith("a1");
});

test("shows how many documents were hidden by access control, and nothing when none were", () => {
  const hidden = [{ id: "salary-bands", title: "Salary Bands", classification: "confidential" }];
  const { rerender } = render(<AssistantMessage {...base} msg={msg({ response: response({ hidden }) })} />);
  expect(screen.getByText("1 document hidden by access control")).toBeInTheDocument();
  rerender(<AssistantMessage {...base} msg={msg({ response: response({ hidden: [...hidden, { ...hidden[0], id: "x" }] }) })} />);
  expect(screen.getByText("2 documents hidden by access control")).toBeInTheDocument();
  rerender(<AssistantMessage {...base} msg={msg()} />);
  expect(screen.queryByText(/hidden by access control/)).toBeNull();
});

test("a flagged answer gets a pink Flagged chip and a blocked one a Blocked chip", () => {
  const flagged = response({ guardrail: { verdict: "FLAGGED", reasons: ["pii_salary"], status: "ok", latency_ms: 30, injection_score: 0.02 } });
  const { rerender } = render(<AssistantMessage {...base} msg={msg({ response: flagged })} />);
  expect(screen.getByRole("button", { name: /^flagged: salary figure/i })).toBeInTheDocument();
  const blocked = response({ blocked: true, answer: "", block_reason: ["prompt_injection"], guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection"], status: "ok", latency_ms: 30, injection_score: 0.9 } });
  rerender(<AssistantMessage {...base} msg={msg({ response: blocked })} />);
  expect(screen.getByRole("button", { name: /^blocked: prompt injection attempt/i })).toBeInTheDocument();
});

test("Ask again names the other persona and calls onAskAgain; Regenerate calls onRegenerate", async () => {
  const onAskAgain = vi.fn();
  const onRegenerate = vi.fn();
  render(<AssistantMessage {...base} onAskAgain={onAskAgain} onRegenerate={onRegenerate} msg={msg()} />);
  await userEvent.click(screen.getByRole("button", { name: "Ask again as Daniel Ong" }));
  expect(onAskAgain).toHaveBeenCalledWith("a1");
  await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
  expect(onRegenerate).toHaveBeenCalledWith("a1");
});

test("both action pills are disabled while a request is pending", () => {
  render(<AssistantMessage {...base} pending msg={msg()} />);
  expect(screen.getByRole("button", { name: "Ask again as Daniel Ong" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Regenerate" })).toBeDisabled();
});

test("there are no thumbs, copy or more buttons and no model or latency line above the answer", () => {
  render(<AssistantMessage {...base} msg={msg()} />);
  expect(screen.queryByRole("button", { name: /copy|helpful|thumb|more/i })).toBeNull();
  expect(screen.queryByText(/FOO CORP HR/i)).toBeNull();
});

test("citations link to Discover for retrieved documents only", () => {
  render(<AssistantMessage {...base} msg={msg({ response: response({ answer: "See [pto-policy] and [ghost]." }) })} />);
  const link = screen.getByRole("link", { name: /Paid Time Off Policy · Confluence/ });
  expect(link.getAttribute("href")).toContain("https://kb.example/app/discover");
  expect(link.getAttribute("href")).toContain(encodeURIComponent("pto-policy").replace(/%2D/g, "-"));
  expect(screen.queryByRole("link", { name: /ghost/ })).toBeNull();
  expect(screen.getByText(/\[ghost\]/)).toBeInTheDocument();
});

test("without a Kibana URL a citation is a button, not a link", () => {
  render(<AssistantMessage {...base} kibanaUrl={undefined} msg={msg()} />);
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.getByRole("button", { name: /Paid Time Off Policy · Confluence/ })).toBeInTheDocument();
});

test("a done answer has no axe violations", async () => {
  const { container } = render(<AssistantMessage {...base} msg={msg()} />);
  expect(await axe(container)).toHaveNoViolations();
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
