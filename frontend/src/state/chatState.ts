import type { ChatResponse, Engine } from "../lib/types";

export type UserMsg = { id: string; kind: "user"; text: string; persona: string };
export type AssistantMsg = {
  id: string; kind: "assistant"; replyTo: string; persona: string; model: string; engine: Engine;
  status: "pending" | "done" | "error"; response?: ChatResponse; error?: { status: number; code: string; hint?: string };
};
export type DividerMsg = { id: string; kind: "divider"; text: string; fromPersona?: string };
export type Message = UserMsg | AssistantMsg | DividerMsg;

export type ChatState = {
  persona: string; model: string; engine: Engine; messages: Message[]; selectedId: string | null; spendUsd: number;
};

export type Action =
  | { type: "setPersona"; persona: string; label: string }
  | { type: "setModel"; model: string }
  | { type: "setEngine"; engine: Engine }
  | { type: "send"; text: string; userId: string; assistantId: string }
  | { type: "receive"; id: string; response: ChatResponse }
  | { type: "fail"; id: string; error: { status: number; code: string; hint?: string } }
  | { type: "retry"; id: string; model?: string }
  | { type: "select"; id: string | null }
  | { type: "reset" };

let counter = 0;
export const newId = (): string => `m${++counter}`;

export function initialState(persona: string, model: string): ChatState {
  return { persona, model, engine: "sdk", messages: [], selectedId: null, spendUsd: 0 };
}

function mapAssistant(
  state: ChatState, id: string, from: AssistantMsg["status"], fn: (a: AssistantMsg) => AssistantMsg,
): ChatState {
  let hit = false;
  const messages = state.messages.map((m) => {
    if (m.kind === "assistant" && m.id === id && m.status === from) {
      hit = true;
      return fn(m);
    }
    return m;
  });
  return hit ? { ...state, messages } : state;
}

export function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "setPersona": {
      if (action.persona === state.persona) return state;
      const last = state.messages[state.messages.length - 1];
      let messages: Message[];
      if (state.messages.length === 0) messages = state.messages;
      else if (last.kind === "divider") {
        // arrowing through the radiogroup selects on every step: keep one divider, or none when we are back where we started
        const from = last.fromPersona ?? "";
        messages = action.persona === from
          ? state.messages.slice(0, -1)
          : [...state.messages.slice(0, -1), { ...last, text: `Now asking as ${action.label}` }];
      } else {
        messages = [...state.messages, { id: newId(), kind: "divider" as const, text: `Now asking as ${action.label}`, fromPersona: state.persona }];
      }
      return { ...state, persona: action.persona, messages };
    }
    case "setModel":
      return { ...state, model: action.model };
    case "setEngine":
      return { ...state, engine: action.engine };
    case "send": {
      const user: UserMsg = { id: action.userId, kind: "user", text: action.text, persona: state.persona };
      const assistant: AssistantMsg = {
        id: action.assistantId, kind: "assistant", replyTo: user.id, persona: state.persona, model: state.model, engine: state.engine, status: "pending",
      };
      return { ...state, messages: [...state.messages, user, assistant], selectedId: assistant.id };
    }
    case "receive": {
      const next = mapAssistant(state, action.id, "pending", (a) => ({ ...a, status: "done", response: action.response, error: undefined }));
      return next === state ? state : { ...next, spendUsd: next.spendUsd + action.response.cost_usd, selectedId: action.id };
    }
    case "fail":
      return mapAssistant(state, action.id, "pending", (a) => ({ ...a, status: "error", error: action.error }));
    case "retry":
      return mapAssistant(state, action.id, "error", (a) => ({ ...a, model: action.model ?? a.model, status: "pending", error: undefined, response: undefined }));
    case "select":
      return { ...state, selectedId: action.id };
    case "reset":
      return initialState(state.persona, state.model);
  }
}

export const pendingCount = (s: ChatState): number => s.messages.filter((m) => m.kind === "assistant" && m.status === "pending").length;

export function lastUserQuestion(s: ChatState): UserMsg | null {
  for (let i = s.messages.length - 1; i >= 0; i--) {
    const m = s.messages[i];
    if (m.kind === "user") return m;
  }
  return null;
}

export function userMessageFor(s: ChatState, assistantId: string): UserMsg | null {
  const a = s.messages.find((m) => m.kind === "assistant" && m.id === assistantId) as AssistantMsg | undefined;
  if (!a) return null;
  return (s.messages.find((m) => m.kind === "user" && m.id === a.replyTo) as UserMsg | undefined) ?? null;
}
