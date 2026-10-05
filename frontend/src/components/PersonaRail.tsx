import { useRef } from "react";
import { motion } from "motion/react";
import { Avatar } from "./Avatar";
import type { Persona } from "../lib/types";

export const personaLabel = (p: Persona) => `${p.name}, ${p.title}`;

type Props = { personas: Persona[]; selected: string; onSelect: (id: string) => void; disabled?: boolean };

const NAV_KEYS = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];

export function PersonaRail({ personas, selected, onSelect, disabled }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (disabled || !NAV_KEYS.includes(e.key)) return;
    e.preventDefault();
    let next: number;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = personas.length - 1;
    else {
      const dir = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1;
      next = (index + dir + personas.length) % personas.length;
    }
    refs.current[next]?.focus();
    onSelect(personas[next].id);
  }

  return (
    <div className="p-4 md:p-5">
      <h2 id="who-asks" className="text-sm font-semibold text-ink">Who is asking</h2>
      <p className="mt-1 text-sm text-muted">Each person can read a different set of documents.</p>

      {personas.length === 0 ? (
        <div data-testid="persona-skeleton" className="mt-4 grid gap-2" aria-hidden>
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-[72px] animate-pulse motion-reduce:animate-none rounded-control bg-canvas" />)}
        </div>
      ) : (
        <div role="radiogroup" aria-labelledby="who-asks" className="mt-4 grid gap-2">
          {personas.map((p, i) => {
            const active = p.id === selected;
            return (
              <button
                key={p.id} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={active}
                tabIndex={active || (!selected && i === 0) ? 0 : -1} disabled={disabled}
                onClick={() => onSelect(p.id)} onKeyDown={(e) => onKeyDown(e, i)}
                className="relative flex w-full items-center gap-3 rounded-control border border-line bg-surface p-3 text-left transition hover:border-blue/50 active:scale-[0.99] disabled:opacity-60"
              >
                {active && (
                  <motion.span
                    layoutId="persona-active" aria-hidden
                    className="absolute inset-0 rounded-control border-2 border-blue bg-blue-soft/50"
                    transition={{ type: "spring", stiffness: 140, damping: 20 }}
                  />
                )}
                <span className="relative flex items-center gap-3">
                  <Avatar name={p.name} />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-ink">{p.name}</span>{" "}
                    <span className="block truncate text-sm text-muted">{p.title}</span>{" "}
                    <span className="mt-0.5 block text-xs text-muted">Reads {p.can_read_docs} of {p.total_docs} documents</span>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
