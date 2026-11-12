import { compressToUTF16, decompressFromUTF16 } from "lz-string";
import type { AssistantMsg, ChatState } from "../state/chatState";

/* Browser-only conversation history. Every storage access is wrapped: the app must work with storage blocked or full. */
export type Conversation = { id: string; title: string; createdAt: number; updatedAt: number; flagged: boolean; state: ChatState };

export const HISTORY_KEY = "glassbox.history.v1";
export const MAX_CONVERSATIONS = 50;
const VERSION = 1;
const DAY = 86_400_000;

const isConversation = (c: unknown): c is Conversation => {
  const x = c as Conversation | null;
  return !!x && typeof x.id === "string" && typeof x.title === "string" && typeof x.createdAt === "number" && typeof x.updatedAt === "number"
    && typeof x.state === "object" && x.state !== null && Array.isArray(x.state.messages);
};

export function loadHistory(): Conversation[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(decompressFromUTF16(raw) ?? "");
    if (!parsed || parsed.v !== VERSION || !Array.isArray(parsed.items)) return [];
    return parsed.items.filter(isConversation).map((c: Conversation) => ({ ...c, flagged: !!c.flagged }));
  } catch {
    return [];
  }
}

function write(list: Conversation[]): boolean {
  try {
    localStorage.setItem(HISTORY_KEY, compressToUTF16(JSON.stringify({ v: VERSION, items: list })));
    return true;
  } catch {
    return false;
  }
}

/** On a quota error, drops the oldest half once and retries. Returns false when nothing could be stored. */
export function saveHistory(list: Conversation[]): boolean {
  if (write(list)) return true;
  const keep = list.slice(0, Math.max(0, list.length - Math.max(1, Math.floor(list.length / 2))));
  return keep.length > 0 && write(keep);
}

export function upsertConversation(list: Conversation[], c: Conversation): Conversation[] {
  return [c, ...list.filter((x) => x.id !== c.id)].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CONVERSATIONS);
}
export const removeConversation = (list: Conversation[], id: string): Conversation[] => list.filter((c) => c.id !== id);
export const renameConversation = (list: Conversation[], id: string, title: string): Conversation[] =>
  list.map((c) => (c.id === id ? { ...c, title } : c));

export function titleFor(question: string): string {
  const t = question.replace(/\s+/g, " ").trim();
  if (!t) return "New chat";
  const chars = Array.from(t);
  return chars.length > 60 ? `${chars.slice(0, 60).join("")}…` : t;
}

export function isFlagged(state: ChatState): boolean {
  return state.messages.some((m) => m.kind === "assistant" && m.status === "done" && !!m.response && (m.response.blocked || m.response.guardrail.verdict === "FLAGGED"));
}

/** A request pending when the page closes must not restore as a spinner that never resolves. */
export function forStorage(state: ChatState): ChatState {
  return {
    ...state,
    messages: state.messages.map((m) =>
      m.kind === "assistant" && m.status === "pending"
        ? ({ ...m, status: "error", error: { status: 0, code: "interrupted" } } as AssistantMsg)
        : m),
  };
}

export function groupByAge(list: Conversation[], now: number): { label: "Today" | "Last 7 days" | "Older"; items: Conversation[] }[] {
  const startOfToday = new Date(now).setHours(0, 0, 0, 0);
  const buckets = { Today: [] as Conversation[], "Last 7 days": [] as Conversation[], Older: [] as Conversation[] };
  for (const c of list) {
    if (c.updatedAt >= startOfToday) buckets.Today.push(c);
    else if (now - c.updatedAt < 7 * DAY) buckets["Last 7 days"].push(c);
    else buckets.Older.push(c);
  }
  return (Object.keys(buckets) as (keyof typeof buckets)[]).filter((l) => buckets[l].length > 0).map((label) => ({ label, items: buckets[label] }));
}
