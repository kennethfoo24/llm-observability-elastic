import { useMemo, useState } from "react";
import { groupByAge, type Conversation } from "../lib/history";
import { EditIcon, MessageIcon, TrashIcon } from "./icons";

type Props = {
  conversations: Conversation[]; activeId: string | null; pending: boolean; query: string;
  onOpen: (id: string) => void; onDelete: (id: string) => void; onRename: (id: string, title: string) => void; onClearAll: () => void;
};

const tool = "grid size-7 place-items-center rounded-full text-ink transition hover:bg-white/70 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-blue";

export function HistoryList({ conversations, activeId, pending, query, onOpen, onDelete, onRename, onClearAll }: Props) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [draft, setDraft] = useState("");
  const q = query.trim().toLowerCase();
  const shown = useMemo(() => (q ? conversations.filter((c) => c.title.toLowerCase().includes(q)) : conversations), [conversations, q]);
  const groups = useMemo(() => groupByAge(shown, Date.now()), [shown]);

  function commitRename(id: string) {
    const t = draft.trim();
    if (t) onRename(id, t);
    setRenamingId(null);
  }

  return (
    <>
      <div className="flex items-center justify-between border-b border-line px-6 pb-3 pt-4 text-[13px] text-muted">
        <h2 className="font-normal">Your conversations</h2>
        <button type="button" disabled={conversations.length === 0 || pending} onClick={() => setConfirmAll(true)} className="font-medium text-blue hover:underline disabled:cursor-not-allowed disabled:opacity-40">
          Clear All
        </button>
      </div>
      {confirmAll && (
        <div role="alertdialog" aria-label="Clear all conversations" className="mx-3 mt-2 flex items-center justify-between gap-2 rounded-2xl bg-flag-soft px-4 py-2 text-[13px] text-flag-ink">
          <span>Delete all conversations?</span>
          <span className="flex gap-1">
            <button type="button" disabled={pending} onClick={() => { setConfirmAll(false); onClearAll(); }} className="rounded-full bg-flag-ink px-3 py-1 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">Yes, clear all</button>
            <button type="button" onClick={() => setConfirmAll(false)} className="rounded-full px-3 py-1 font-medium">Cancel</button>
          </span>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {conversations.length === 0 && <p className="px-3 py-4 text-sm text-muted">Conversations you start will appear here.</p>}
        {conversations.length > 0 && shown.length === 0 && <p className="px-3 py-4 text-sm text-muted">No conversations match.</p>}
        {groups.map((g, gi) => (
          <section key={g.label} aria-label={g.label}>
            <h3 className={`px-3 pb-2 pt-3 text-[13px] font-normal text-muted ${gi > 0 ? "mt-2 border-t border-line" : ""}`}>{g.label}</h3>
            <ul>
              {g.items.map((c) => {
                const active = c.id === activeId;
                return (
                  <li key={c.id} className={`group flex items-center gap-1 rounded-2xl pr-2 ${active ? "bg-blue-soft text-blue" : "text-ink hover:bg-canvas"}`}>
                    {renamingId === c.id ? (
                      <input
                        autoFocus aria-label="Rename conversation" value={draft} onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") commitRename(c.id); if (e.key === "Escape") { e.preventDefault(); setRenamingId(null); } }}
                        onBlur={() => setRenamingId(null)}
                        className="m-1 min-w-0 flex-1 rounded-xl border border-line bg-white px-3 py-2 text-[15px] text-ink outline-none focus:border-blue"
                      />
                    ) : (
                      <button
                        type="button" disabled={pending} onClick={() => onOpen(c.id)} aria-current={active ? "true" : undefined}
                        className={`flex min-w-0 flex-1 items-center gap-3 rounded-2xl px-3 py-3 text-left text-[15px] disabled:cursor-not-allowed disabled:opacity-60 ${active ? "font-medium" : ""}`}
                      >
                        <MessageIcon size={18} className="shrink-0" />
                        <span className="truncate">{c.title}</span>
                        {c.flagged && <span title="Blocked or flagged" className="ml-auto size-1.5 shrink-0 rounded-full bg-flag" />}
                      </button>
                    )}
                    {confirmId === c.id ? (
                      <span className="flex shrink-0 gap-1 text-xs">
                        <button type="button" disabled={pending} onClick={() => { setConfirmId(null); onDelete(c.id); }} className="rounded-full bg-flag-ink px-2 py-1 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">Confirm delete</button>
                        <button type="button" onClick={() => setConfirmId(null)} className="rounded-full px-2 py-1 font-medium text-ink">Cancel</button>
                      </span>
                    ) : (
                      <span className={`shrink-0 gap-1 ${active ? "flex" : "hidden group-hover:flex group-focus-within:flex"}`}>
                        <button type="button" aria-label={`Delete ${c.title}`} disabled={pending} onClick={() => setConfirmId(c.id)} className={tool}><TrashIcon size={15} /></button>
                        <button type="button" aria-label={`Rename ${c.title}`} disabled={pending} onClick={() => { setDraft(c.title); setRenamingId(c.id); }} className={tool}><EditIcon size={15} /></button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
