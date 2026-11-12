import { useCallback, useRef, useState } from "react";
import { loadHistory, removeConversation, renameConversation, saveHistory, upsertConversation, type Conversation } from "../lib/history";

/** The saved conversations, kept in step with browser storage. Loaded once; storage failures never throw. */
export function useHistory() {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadHistory());
  const latest = useRef(conversations);

  const commit = useCallback((next: Conversation[]) => {
    latest.current = next;
    setConversations(next);
    saveHistory(next);
  }, []);

  const upsert = useCallback((c: Conversation) => commit(upsertConversation(latest.current, c)), [commit]);
  const remove = useCallback((id: string) => commit(removeConversation(latest.current, id)), [commit]);
  const rename = useCallback((id: string, title: string) => commit(renameConversation(latest.current, id, title)), [commit]);
  const clear = useCallback(() => commit([]), [commit]);

  return { conversations, upsert, remove, rename, clear };
}
