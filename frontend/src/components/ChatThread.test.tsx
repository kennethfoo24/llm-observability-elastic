import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatThread } from "./ChatThread";
import type { Message } from "../state/chatState";
import type { Persona } from "../lib/types";

const personas: Persona[] = [
  { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 },
  { id: "manager", name: "Daniel Ong", title: "Engineering Manager", can_read_docs: 11, total_docs: 20 },
];
const base = {
  models: [], personas, pending: false, selectedId: null, kibanaUrl: "https://kb.example",
  onSelect: vi.fn(), onCitation: vi.fn(), onRetry: vi.fn(), onAskAgain: vi.fn(), onRegenerate: vi.fn(), onOpenDetails: vi.fn(), onEdit: vi.fn(),
};

const thread: Message[] = [
  { id: "m1", kind: "user", text: "What are the salary bands for L3 to L5?", persona: "employee" },
  { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: "pending" },
  { id: "m3", kind: "divider", text: "Now asking as Daniel Ong, Engineering Manager" },
];

test("renders user messages, pending answers and persona dividers in a polite live log", () => {
  render(<ChatThread {...base} messages={thread} />);
  expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
  expect(screen.getByText(/salary bands for L3 to L5/i)).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(screen.getByText("Now asking as Daniel Ong, Engineering Manager")).toBeInTheDocument();
});

test("the divider no longer carries an ask-again button (it lives under each answer)", () => {
  render(<ChatThread {...base} messages={thread} />);
  expect(screen.queryByRole("button", { name: /ask again/i })).toBeNull();
});

test("a done answer offers Ask again as the persona who did not ask it", async () => {
  const onAskAgain = vi.fn();
  render(<ChatThread {...base} onAskAgain={onAskAgain} messages={[
    { id: "m1", kind: "user", text: "q", persona: "employee" },
    { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: "done", response: {
      answer: "ok", blocked: false, block_reason: [], trace_id: "t", persona: "employee", model: "m", engine: "sdk", docs: [], hidden: [],
      usage: { input_tokens: 1, output_tokens: 1, thinking_tokens: 0 }, cost_usd: 0.001,
      guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 1, injection_score: 0 }, stages: [] } },
  ]} />);
  await userEvent.click(screen.getByRole("button", { name: "Ask again as Daniel Ong" }));
  expect(onAskAgain).toHaveBeenCalledWith("m2");
});

test("an answer keeps the persona it was asked as, even after a switch", () => {
  render(<ChatThread {...base} messages={[
    { id: "m1", kind: "user", text: "q", persona: "employee" },
    { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: "error", error: { status: 502, code: "upstream_error" } },
  ]} />);
  expect(screen.getByRole("article", { name: "Answer for Maya Lim" })).toBeInTheDocument();
});

test("each answer is labelled with the persona it was asked as, in a mixed-persona thread", () => {
  render(<ChatThread {...base} messages={[
    { id: "m1", kind: "user", text: "q1", persona: "employee" },
    { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: "pending" },
    { id: "m3", kind: "divider", text: "Now asking as Daniel Ong, Engineering Manager" },
    { id: "m4", kind: "user", text: "q1", persona: "manager" },
    { id: "m5", kind: "assistant", replyTo: "m4", persona: "manager", model: "eis-gpt-mini", engine: "sdk", status: "error", error: { status: 502, code: "upstream_error" } },
  ]} />);
  expect(screen.getByRole("article", { name: "Answer for Maya Lim" })).toBeInTheDocument();
  expect(screen.getByRole("article", { name: "Answer for Daniel Ong" })).toBeInTheDocument();
});

test("the edit button on a question puts its text back via onEdit", async () => {
  const onEdit = vi.fn();
  render(<ChatThread {...base} onEdit={onEdit} messages={thread} />);
  await userEvent.click(screen.getByRole("button", { name: "Edit and resend" }));
  expect(onEdit).toHaveBeenCalledWith("What are the salary bands for L3 to L5?");
});

test("scrolls to the end again when the pending answer lands", () => {
  const spy = vi.fn();
  Element.prototype.scrollIntoView = spy;
  const pending: Message[] = [
    { id: "m1", kind: "user", text: "q", persona: "employee" },
    { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: "pending" },
  ];
  const { rerender } = render(<ChatThread {...base} messages={pending} />);
  const before = spy.mock.calls.length;
  rerender(<ChatThread {...base} messages={[pending[0], { ...(pending[1] as any), status: "error", error: { status: 502, code: "upstream_error" } }]} />);
  expect(spy.mock.calls.length).toBeGreaterThan(before);
  delete (Element.prototype as any).scrollIntoView;
});
