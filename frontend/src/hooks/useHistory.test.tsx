import { act, renderHook } from "@testing-library/react";
import { HISTORY_KEY, loadHistory, saveHistory, type Conversation } from "../lib/history";
import { useHistory } from "./useHistory";

const conv = (id: string, updatedAt: number): Conversation => ({
  id, title: id, createdAt: updatedAt, updatedAt, flagged: false,
  state: { persona: "employee", model: "m", engine: "langchain", messages: [], selectedId: null, spendUsd: 0 },
});

beforeEach(() => localStorage.clear());

test("upsert, rename, remove and clear update the list and storage", () => {
  const { result } = renderHook(() => useHistory());
  act(() => result.current.upsert(conv("a", 1)));
  act(() => result.current.upsert(conv("b", 2)));
  expect(result.current.conversations.map((c) => c.id)).toEqual(["b", "a"]);
  act(() => result.current.rename("a", "Renamed"));
  expect(loadHistory().find((c) => c.id === "a")?.title).toBe("Renamed");
  act(() => result.current.remove("b"));
  expect(loadHistory().map((c) => c.id)).toEqual(["a"]);
  act(() => result.current.clear());
  expect(result.current.conversations).toEqual([]);
  expect(loadHistory()).toEqual([]);
});

test("loads saved history on mount", () => {
  saveHistory([conv("x", 5)]);
  const { result } = renderHook(() => useHistory());
  expect(result.current.conversations.map((c) => c.id)).toEqual(["x"]);
});

test("starts empty when storage is corrupt", () => {
  localStorage.setItem(HISTORY_KEY, "garbage");
  const { result } = renderHook(() => useHistory());
  expect(result.current.conversations).toEqual([]);
});
