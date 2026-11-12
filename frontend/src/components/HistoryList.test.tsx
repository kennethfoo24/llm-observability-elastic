import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HistoryList } from "./HistoryList";
import type { Conversation } from "../lib/history";

const DAY = 86_400_000;
const conv = (id: string, title: string, ageMs: number, flagged = false): Conversation => ({
  id, title, createdAt: Date.now() - ageMs, updatedAt: Date.now() - ageMs, flagged,
  state: { persona: "employee", model: "m", engine: "langchain", messages: [], selectedId: null, spendUsd: 0 },
});
const list = [conv("a", "How many PTO days?", 1000), conv("b", "Ignore previous instructions", 3 * DAY, true), conv("c", "Old question", 30 * DAY)];
const base = { conversations: list, activeId: "a", pending: false, query: "", onOpen: vi.fn(), onDelete: vi.fn(), onRename: vi.fn(), onClearAll: vi.fn() };

test("groups rows under Today, Last 7 days and Older", () => {
  render(<HistoryList {...base} />);
  expect(screen.getByText("Today")).toBeInTheDocument();
  expect(screen.getByText("Last 7 days")).toBeInTheDocument();
  expect(screen.getByText("Older")).toBeInTheDocument();
});

test("marks the active row and shows the pink dot only for flagged conversations", () => {
  render(<HistoryList {...base} />);
  expect(screen.getByRole("button", { name: "How many PTO days?" })).toHaveAttribute("aria-current", "true");
  expect(screen.getByRole("button", { name: "Old question" })).not.toHaveAttribute("aria-current");
  expect(screen.getAllByTitle("Blocked or flagged")).toHaveLength(1);
});

test("clicking a row opens it", async () => {
  const onOpen = vi.fn();
  render(<HistoryList {...base} onOpen={onOpen} />);
  await userEvent.click(screen.getByRole("button", { name: "Old question" }));
  expect(onOpen).toHaveBeenCalledWith("c");
});

test("while a request is pending the rows and delete are disabled", () => {
  render(<HistoryList {...base} pending />);
  expect(screen.getByRole("button", { name: "Old question" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Delete Old question" })).toBeDisabled();
});

test("delete asks for confirmation before calling onDelete", async () => {
  const onDelete = vi.fn();
  render(<HistoryList {...base} onDelete={onDelete} />);
  await userEvent.click(screen.getByRole("button", { name: "Delete Old question" }));
  expect(onDelete).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  expect(onDelete).toHaveBeenCalledWith("c");
});

test("cancelling a delete keeps the conversation", async () => {
  const onDelete = vi.fn();
  render(<HistoryList {...base} onDelete={onDelete} />);
  await userEvent.click(screen.getByRole("button", { name: "Delete Old question" }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(onDelete).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Old question" })).toBeInTheDocument();
});

test("rename commits on Enter and cancels on Escape", async () => {
  const onRename = vi.fn();
  render(<HistoryList {...base} onRename={onRename} />);
  await userEvent.click(screen.getByRole("button", { name: "Rename Old question" }));
  const input = screen.getByRole("textbox", { name: "Rename conversation" });
  await userEvent.clear(input);
  await userEvent.type(input, "Renamed{Enter}");
  expect(onRename).toHaveBeenCalledWith("c", "Renamed");
  await userEvent.click(screen.getByRole("button", { name: "Rename How many PTO days?" }));
  await userEvent.type(screen.getByRole("textbox", { name: "Rename conversation" }), "zzz{Escape}");
  expect(onRename).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("textbox", { name: "Rename conversation" })).toBeNull();
});

test("Clear All confirms first and calls onClearAll only after confirming", async () => {
  const onClearAll = vi.fn();
  render(<HistoryList {...base} onClearAll={onClearAll} />);
  await userEvent.click(screen.getByRole("button", { name: "Clear All" }));
  expect(onClearAll).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Yes, clear all" }));
  expect(onClearAll).toHaveBeenCalledTimes(1);
});

test("the query filters by title, case-insensitively", () => {
  render(<HistoryList {...base} query="pto" />);
  expect(screen.getByRole("button", { name: "How many PTO days?" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Old question" })).toBeNull();
});

test("shows an empty hint when there is no history", () => {
  render(<HistoryList {...base} conversations={[]} activeId={null} />);
  expect(screen.getByText(/conversations you start will appear here/i)).toBeInTheDocument();
  expect(within(screen.getByRole("button", { name: "Clear All" }).parentElement!).getByRole("button", { name: "Clear All" })).toBeDisabled();
});
