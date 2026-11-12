import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  HISTORY_KEY, MAX_CONVERSATIONS, forStorage, groupByAge, isFlagged, loadHistory, removeConversation, renameConversation,
  saveHistory, titleFor, upsertConversation, type Conversation,
} from "./history";
import type { AssistantMsg, ChatState } from "../state/chatState";
import type { ChatResponse } from "../lib/types";

const DAY = 86_400_000;
const NOW = Date.UTC(2026, 10, 12, 12, 0, 0);

const resp = (over: Partial<ChatResponse> = {}, verdict = "PASS") =>
  ({ answer: "a", blocked: false, block_reason: [], docs: [], hidden: [], stages: [], cost_usd: 0.001, guardrail: { verdict, status: "ok", reasons: [] }, ...over }) as unknown as ChatResponse;

const assistant = (id: string, status: AssistantMsg["status"], response?: ChatResponse): AssistantMsg =>
  ({ id, kind: "assistant", replyTo: "u", persona: "employee", model: "eis-gpt-mini", engine: "langchain", status, response });

const state = (messages: ChatState["messages"] = []): ChatState =>
  ({ persona: "employee", model: "eis-gpt-mini", engine: "langchain", messages, selectedId: null, spendUsd: 0 });

const conv = (id: string, updatedAt: number, over: Partial<Conversation> = {}): Conversation =>
  ({ id, title: id, createdAt: updatedAt, updatedAt, flagged: false, state: state(), ...over });

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("loadHistory", () => {
  it("returns [] for invalid JSON", () => {
    localStorage.setItem(HISTORY_KEY, "{not json");
    expect(loadHistory()).toEqual([]);
  });
  it("returns [] for a wrong-version payload", () => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify({ v: 99, items: [conv("a", 1)] }));
    expect(loadHistory()).toEqual([]);
  });
  it("returns [] when the payload is not an array of items", () => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify({ v: 1, items: "nope" }));
    expect(loadHistory()).toEqual([]);
  });
  it("returns [] when getItem throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(loadHistory()).toEqual([]);
  });
  it("round-trips through saveHistory", () => {
    const list = [conv("a", 2), conv("b", 1)];
    expect(saveHistory(list)).toBe(true);
    expect(loadHistory()).toEqual(list);
  });
});

describe("saveHistory", () => {
  it("retries after dropping the oldest when setItem throws once", () => {
    const real = Storage.prototype.setItem;
    let calls = 0;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, k: string, v: string) {
      if (++calls === 1) throw new DOMException("full", "QuotaExceededError");
      return real.call(this, k, v);
    });
    const list = [conv("new", 3), conv("mid", 2), conv("old", 1)];
    expect(saveHistory(list)).toBe(true);
    const saved = loadHistory();
    expect(saved.length).toBeLessThan(3);
    expect(saved[0].id).toBe("new");
  });
  it("returns false and does not throw when setItem always throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    expect(saveHistory([conv("a", 1)])).toBe(false);
  });
});

describe("list operations", () => {
  it("upsert replaces by id and moves it first", () => {
    const out = upsertConversation([conv("a", 2), conv("b", 1)], conv("b", 5, { title: "renamed by upsert" }));
    expect(out.map((c) => c.id)).toEqual(["b", "a"]);
    expect(out[0].title).toBe("renamed by upsert");
  });
  it("caps at 50, dropping the oldest", () => {
    let list: Conversation[] = [];
    for (let i = 0; i < MAX_CONVERSATIONS + 5; i++) list = upsertConversation(list, conv(`c${i}`, i));
    expect(list).toHaveLength(MAX_CONVERSATIONS);
    expect(list[0].id).toBe(`c${MAX_CONVERSATIONS + 4}`);
    expect(list.some((c) => c.id === "c0")).toBe(false);
  });
  it("remove and rename", () => {
    const list = [conv("a", 2), conv("b", 1)];
    expect(removeConversation(list, "a").map((c) => c.id)).toEqual(["b"]);
    expect(renameConversation(list, "a", "Hello")[0].title).toBe("Hello");
  });
});

describe("titleFor", () => {
  it("collapses whitespace", () => expect(titleFor("  hello\n\n  world  ")).toBe("hello world"));
  it("truncates long questions", () => {
    const t = titleFor("x".repeat(200));
    expect(t.endsWith("…")).toBe(true);
    expect(t.length).toBeLessThanOrEqual(61);
  });
  it("falls back for blank input", () => expect(titleFor("   ")).toBe("New chat"));
});

describe("forStorage", () => {
  it("turns pending answers into interrupted errors and leaves done ones", () => {
    const s = forStorage(state([assistant("p", "pending"), assistant("d", "done", resp())]));
    const [p, d] = s.messages as AssistantMsg[];
    expect(p.status).toBe("error");
    expect(p.error).toEqual({ status: 0, code: "interrupted" });
    expect(d.status).toBe("done");
  });
});

describe("isFlagged", () => {
  it("is true for blocked and for FLAGGED answers", () => {
    expect(isFlagged(state([assistant("a", "done", resp({ blocked: true }))]))).toBe(true);
    expect(isFlagged(state([assistant("a", "done", resp({}, "FLAGGED"))]))).toBe(true);
  });
  it("is false for clean conversations", () => {
    expect(isFlagged(state([assistant("a", "done", resp())]))).toBe(false);
  });
});

describe("groupByAge", () => {
  it("groups Today, Last 7 days and Older, omitting empty groups", () => {
    const groups = groupByAge([conv("t", NOW - 1000), conv("w", NOW - 3 * DAY), conv("o", NOW - 30 * DAY)], NOW);
    expect(groups.map((g) => g.label)).toEqual(["Today", "Last 7 days", "Older"]);
    expect(groups.map((g) => g.items[0].id)).toEqual(["t", "w", "o"]);
    expect(groupByAge([conv("t", NOW)], NOW).map((g) => g.label)).toEqual(["Today"]);
  });
});
