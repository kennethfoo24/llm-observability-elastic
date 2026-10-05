import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { initialState, lastUserQuestion, newId, pendingCount, reducer, userMessageFor, type AssistantMsg } from "../state/chatState";
import { usePolling } from "./usePolling";
import type { ModelInfo, Persona } from "../lib/types";
import { personaLabel } from "../components/PersonaRail";

type DraftControl = readonly [string, (v: string) => void];

/* `draftControl` lets a parent own the composer draft so it survives this hook's owner unmounting (a 401 returns to the gate). */
export function useChatSession(personas: Persona[], models: ModelInfo[], refreshModels: () => void, draftControl?: DraftControl) {
  const [state, dispatch] = useReducer(reducer, undefined, () => initialState(personas[0]?.id ?? "", models.find((m) => m.available)?.key ?? models[0]?.key ?? ""));
  const [ownDraft, setOwnDraft] = useState("");
  const [draft, setDraft] = draftControl ?? [ownDraft, setOwnDraft];
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const setDraftRef = useRef(setDraft);
  setDraftRef.current = setDraft;
  const [highlightDocId, setHighlight] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const refreshRef = useRef(refreshModels);
  refreshRef.current = refreshModels;
  const stateRef = useRef(state);
  stateRef.current = state;

  // adopt the first persona once it loads
  useEffect(() => {
    if (!state.persona && personas[0]) dispatch({ type: "setPersona", persona: personas[0].id, label: personaLabel(personas[0]) });
  }, [personas, state.persona]);
  // fall back to an available model when the selected one is missing or offline
  useEffect(() => {
    const current = models.find((m) => m.key === state.model);
    if (!current || !current.available) {
      const fallback = models.find((m) => m.available);
      if (fallback && fallback.key !== state.model) dispatch({ type: "setModel", model: fallback.key });
    }
  }, [models, state.model]);

  const gemmaRelevant = models.some((m) => m.provider === "gemma" && (m.key === state.model || !m.available));
  usePolling(refreshModels, 15000, gemmaRelevant);

  const personaObj = personas.find((p) => p.id === state.persona);
  const personaName = useCallback((id: string) => personas.find((p) => p.id === id)?.name ?? id, [personas]);

  const run = useCallback(async (id: string, req: { message: string; persona: string; model: string; engine: AssistantMsg["engine"] }) => {
    try {
      const response = await api.chat(req);
      dispatch({ type: "receive", id, response });
      return true;
    } catch (e) {
      const err = e instanceof ApiError ? { status: e.status, code: e.code, hint: e.hint } : { status: 0, code: "network_error" };
      dispatch({ type: "fail", id, error: err });
      // flip the Gemma control to Offline now instead of waiting for the poll
      if (err.code === "gemma_offline" || err.status === 503) refreshRef.current();
      return false;
    }
  }, []);

  const send = useCallback(async (text: string) => {
    const t = text.trim();
    const s = stateRef.current;
    if (!t || pendingCount(s) > 0) return;
    const req = { message: t, persona: s.persona, model: s.model, engine: s.engine };
    const userId = newId();
    const assistantId = newId();
    dispatch({ type: "send", text: t, userId, assistantId });
    const ok = await run(assistantId, req);
    // only clear what was sent; text typed while waiting stays
    if (ok && draftRef.current.trim() === t) setDraftRef.current("");
  }, [run]);

  const retry = useCallback(async (id: string) => {
    const s = stateRef.current;
    const a = s.messages.find((m) => m.kind === "assistant" && m.id === id) as AssistantMsg | undefined;
    const q = userMessageFor(s, id);
    if (!a || !q || pendingCount(s) > 0) return;
    dispatch({ type: "retry", id });
    await run(id, { message: q.text, persona: a.persona, model: a.model, engine: a.engine });
  }, [run]);

  const askAgain = useCallback((text: string) => { void send(text); }, [send]);

  const selectCitation = useCallback((docId: string, msgId: string) => {
    dispatch({ type: "select", id: msgId });
    setHighlight(docId);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setHighlight(null), 2500);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);

  const current = useMemo(
    () => (state.messages.find((m) => m.kind === "assistant" && m.id === state.selectedId) as AssistantMsg | undefined) ?? null,
    [state.messages, state.selectedId],
  );
  const question = current ? userMessageFor(state, current.id)?.text : lastUserQuestion(state)?.text;

  return { state, dispatch, send, retry, askAgain, selectCitation, highlightDocId, draft, setDraft, pending: pendingCount(state) > 0, current, question, personaObj, personaName };
}
