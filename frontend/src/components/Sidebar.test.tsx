import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { Sidebar } from "./Sidebar";
import type { Conversation } from "../lib/history";
import type { ModelInfo, Persona } from "../lib/types";

const people: Persona[] = [{ id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 }];
const models: ModelInfo[] = [{ key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis", model_id: "gpt-5.4-mini", available: true }];
const conv: Conversation = {
  id: "a", title: "How many PTO days?", createdAt: Date.now(), updatedAt: Date.now(), flagged: false,
  state: { persona: "employee", model: "eis-gpt-mini", engine: "langchain", messages: [], selectedId: null, spendUsd: 0 },
};
const props = {
  conversations: [conv], activeId: "a", pending: false, personas: people, selectedPersona: "employee", models, selectedModel: "eis-gpt-mini",
  onNewChat: vi.fn(), onOpen: vi.fn(), onDelete: vi.fn(), onRename: vi.fn(), onClearAll: vi.fn(), onPersona: vi.fn(), onModel: vi.fn(),
};

test("shows the wordmark without a plus sign", () => {
  render(<Sidebar {...props} />);
  expect(screen.getByRole("heading", { name: "FOO CORP HR" })).toBeInTheDocument();
});

test("New chat calls onNewChat and is disabled while pending", async () => {
  const onNewChat = vi.fn();
  const { rerender } = render(<Sidebar {...props} onNewChat={onNewChat} />);
  await userEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(onNewChat).toHaveBeenCalledTimes(1);
  rerender(<Sidebar {...props} onNewChat={onNewChat} pending />);
  expect(screen.getByRole("button", { name: "New chat" })).toBeDisabled();
});

test("the search button reveals a field that filters the history", async () => {
  render(<Sidebar {...props} conversations={[conv, { ...conv, id: "b", title: "Remote work" }]} />);
  await userEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await userEvent.type(screen.getByRole("searchbox", { name: "Search conversations" }), "remote");
  expect(screen.queryByRole("button", { name: "How many PTO days?" })).toBeNull();
  expect(screen.getByRole("button", { name: "Remote work" })).toBeInTheDocument();
});

test("holds the model and persona pills at the bottom", () => {
  render(<Sidebar {...props} />);
  expect(screen.getByRole("button", { name: "Model: GPT-5.4 mini" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Asking as Maya Lim/ })).toBeInTheDocument();
});

test("has no axe violations", async () => {
  const { container } = render(<Sidebar {...props} />);
  expect(await axe(container)).toHaveNoViolations();
});
