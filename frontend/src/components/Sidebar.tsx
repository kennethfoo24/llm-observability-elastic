import { useState } from "react";
import { HistoryList } from "./HistoryList";
import { ModelPicker } from "./ModelPicker";
import { PersonaPicker } from "./PersonaPicker";
import { AddIcon, SearchIcon } from "./icons";
import type { Conversation } from "../lib/history";
import type { ModelInfo, Persona } from "../lib/types";

type Props = {
  conversations: Conversation[]; activeId: string | null; pending: boolean;
  personas: Persona[]; selectedPersona: string; models: ModelInfo[]; selectedModel: string;
  onNewChat: () => void; onOpen: (id: string) => void; onDelete: (id: string) => void; onRename: (id: string, title: string) => void;
  onClearAll: () => void; onPersona: (id: string) => void; onModel: (key: string) => void;
};

/* The floating white card on the left: wordmark, New chat, history, then the model and persona pills. */
export function Sidebar(p: Props) {
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");
  return (
    <aside aria-label="Conversations" className="flex h-full min-h-0 flex-col rounded-[24px] bg-white shadow-[0_10px_40px_rgba(17,24,39,.05)]">
      <h1 className="px-[26px] pt-7 text-2xl font-normal uppercase leading-none tracking-[0.2em] text-ink">FOO CORP HR</h1>
      <div className="px-6 pb-4 pt-7">
        <div className="flex gap-2.5">
          <button type="button" onClick={p.onNewChat} disabled={p.pending} className="flex h-12 flex-1 items-center justify-center gap-2 rounded-full bg-blue text-[15px] font-medium text-white transition hover:bg-blue-strong disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue">
            <AddIcon size={18} /> New chat
          </button>
          <button
            type="button" aria-label="Search conversations" aria-expanded={searching}
            onClick={() => { setSearching((s) => !s); setQuery(""); }}
            className="grid size-12 place-items-center rounded-full bg-ink text-white transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
          >
            <SearchIcon size={18} />
          </button>
        </div>
        {searching && (
          <input
            type="search" role="searchbox" aria-label="Search conversations" autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search conversations"
            className="mt-3 w-full rounded-full border border-line bg-canvas px-4 py-2.5 text-sm text-ink outline-none focus:border-blue"
          />
        )}
      </div>
      <HistoryList conversations={p.conversations} activeId={p.activeId} pending={p.pending} query={query} onOpen={p.onOpen} onDelete={p.onDelete} onRename={p.onRename} onClearAll={p.onClearAll} />
      <div className="grid gap-2.5 px-4 pb-4 pt-3">
        <ModelPicker models={p.models} selected={p.selectedModel} onChange={p.onModel} />
        <PersonaPicker personas={p.personas} selected={p.selectedPersona} onChange={p.onPersona} />
      </div>
    </aside>
  );
}
