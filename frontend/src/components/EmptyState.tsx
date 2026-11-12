import { motion } from "motion/react";
import type { Persona } from "../lib/types";

export function EmptyState({ persona, suggestions, onPick }: { persona: Persona | undefined; suggestions: string[]; onPick: (q: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-6 text-center">
      <svg viewBox="0 0 48 48" width={46} height={46} fill="currentColor" aria-hidden className="text-ink">
        <path d="M18 6c1.2 7.6 4.4 10.8 12 12-7.6 1.2-10.8 4.4-12 12-1.2-7.6-4.4-10.8-12-12 7.6-1.2 10.8-4.4 12-12Z" />
        <path d="M35 20c.8 4.6 2.4 6.2 7 7-4.6.8-6.2 2.4-7 7-.8-4.6-2.4-6.2-7-7 4.6-.8 6.2-2.4 7-7Z" />
        <path d="M17 33c.6 3.2 1.8 4.4 5 5-3.2.6-4.4 1.8-5 5-.6-3.2-1.8-4.4-5-5 3.2-.6 4.4-1.8 5-5Z" />
      </svg>
      <h2 className="mb-2 mt-6 text-[32px] font-normal tracking-tight text-ink">Ask anything</h2>
      {persona && (
        <p className="text-[15px] text-muted">
          Asking as <b className="font-medium text-ink">{persona.name}</b>, {persona.title} · reads {persona.can_read_docs} of {persona.total_docs} documents
        </p>
      )}
      {suggestions.length > 0 && (
        <ul className="mt-8 flex max-w-[640px] flex-wrap justify-center gap-2.5">
          {suggestions.map((q, i) => (
            <motion.li key={q} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 140, damping: 20, delay: i * 0.05 }}>
              <button
                type="button" onClick={() => onPick(q)}
                className="rounded-full bg-white/75 px-[18px] py-[11px] text-sm text-ink shadow-[0_2px_10px_rgba(17,24,39,.05)] backdrop-blur transition hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
              >
                {q}
              </button>
            </motion.li>
          ))}
        </ul>
      )}
    </div>
  );
}
