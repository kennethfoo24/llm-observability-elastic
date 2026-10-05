import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatThread } from "./ChatThread";
import type { Message } from "../state/chatState";

const base = { selectedId: null, onSelect: vi.fn(), onCitation: vi.fn(), onRetry: vi.fn(), onAskAgain: vi.fn(), personaName: (id: string) => ({ employee: "Maya Lim", exec: "Rachel Tan" } as Record<string, string>)[id] ?? id };

const thread: Message[] = [
  { id: "m1", kind: "user", text: "What is the Project Aurora severance budget?", persona: "employee" },
  { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "flash-lite", engine: "sdk", status: "pending" },
  { id: "m3", kind: "divider", text: "Now asking as Rachel Tan, Chief People Officer" },
];

test("renders user messages, pending answers and persona dividers in a polite live log", () => {
  render(<ChatThread {...base} messages={thread} askAgainAs="Rachel Tan" />);
  expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
  expect(screen.getByText(/project aurora severance/i)).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(screen.getByText("Now asking as Rachel Tan, Chief People Officer")).toBeInTheDocument();
});

test("after a persona switch it offers to ask the same question again as the new persona", async () => {
  const onAskAgain = vi.fn();
  render(<ChatThread {...base} onAskAgain={onAskAgain} messages={thread} askAgainAs="Rachel Tan" />);
  await userEvent.click(screen.getByRole("button", { name: /ask again as rachel tan/i }));
  expect(onAskAgain).toHaveBeenCalledWith("What is the Project Aurora severance budget?");
});

test("no ask-again offer without a previous question", () => {
  render(<ChatThread {...base} messages={[{ id: "m3", kind: "divider", text: "Now asking as Rachel Tan, Chief People Officer" }]} askAgainAs="Rachel Tan" />);
  expect(screen.queryByRole("button", { name: /ask again/i })).toBeNull();
});

test("an answer keeps the persona it was asked as, even after a switch", () => {
  render(<ChatThread {...base} messages={[
    { id: "m1", kind: "user", text: "q", persona: "employee" },
    { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "flash-lite", engine: "sdk", status: "error", error: { status: 502, code: "upstream_error" } },
  ]} askAgainAs="Rachel Tan" />);
  expect(screen.getByText(/maya lim/i)).toBeInTheDocument();
});

test("each answer shows the persona it was asked as, in a mixed-persona thread", () => {
  render(<ChatThread {...base} askAgainAs="Rachel Tan" messages={[
    { id: "m1", kind: "user", text: "q1", persona: "employee" },
    { id: "m2", kind: "assistant", replyTo: "m1", persona: "employee", model: "flash-lite", engine: "sdk", status: "pending" },
    { id: "m3", kind: "divider", text: "Now asking as Rachel Tan, Chief People Officer" },
    { id: "m4", kind: "user", text: "q1", persona: "exec" },
    { id: "m5", kind: "assistant", replyTo: "m4", persona: "exec", model: "flash-lite", engine: "sdk", status: "error", error: { status: 502, code: "upstream_error" } },
  ]} />);
  expect(screen.getByText("Asked as Maya Lim")).toBeInTheDocument();
  expect(screen.getByText("Asked as Rachel Tan")).toBeInTheDocument();
});
