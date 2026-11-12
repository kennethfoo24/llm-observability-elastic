import { useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { Avatar } from "./Avatar";
import { ChevronUpIcon, TickCircleIcon } from "./icons";
import type { Persona } from "../lib/types";

const NAV_KEYS = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];

export function PersonaPicker({ personas, selected, onChange, disabled }: { personas: Persona[]; selected: string; onChange: (id: string) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = personas.find((p) => p.id === selected);

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (disabled || !NAV_KEYS.includes(e.key)) return;
    e.preventDefault();
    let next: number;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = personas.length - 1;
    else next = (index + (e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1) + personas.length) % personas.length;
    refs.current[next]?.focus();
    onChange(personas[next].id);
  }

  if (personas.length === 0) return <div data-testid="persona-skeleton" aria-hidden className="h-[50px] animate-pulse rounded-full bg-canvas motion-reduce:animate-none" />;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        aria-label={`Asking as ${current ? `${current.name}, ${current.title}` : "nobody"}`}
        className="flex h-[50px] w-full items-center gap-3 rounded-full border border-line bg-white px-[9px] text-left text-[15px] text-ink shadow-[0_2px_8px_rgba(17,24,39,.04)] transition hover:border-field focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
      >
        <Avatar name={current?.name ?? "?"} personaId={current?.id} size={34} />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate">{current?.name}</span>
          <small className="block truncate text-xs text-muted">{current?.title}</small>
        </span>
        <ChevronUpIcon size={15} className="mr-2 shrink-0 text-muted" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content aria-label="Choose who is asking" side="top" align="center" sideOffset={8} collisionPadding={12} className="z-30 w-[var(--radix-popover-trigger-width)] rounded-[20px] bg-white p-2 shadow-[0_18px_50px_rgba(17,24,39,.16),0_0_0_1px_var(--color-line)]">
          <p id="who-asks" className="px-2.5 pb-1 pt-2 text-xs font-medium text-muted">Who is asking</p>
          <div role="radiogroup" aria-labelledby="who-asks" className="grid gap-0.5">
            {personas.map((p, i) => {
              const active = p.id === selected;
              return (
                <button
                  key={p.id} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={active} disabled={disabled}
                  tabIndex={active || (!selected && i === 0) ? 0 : -1} onKeyDown={(e) => onKeyDown(e, i)}
                  onClick={() => { onChange(p.id); setOpen(false); }}
                  className={`flex items-center gap-3 rounded-[14px] p-2.5 text-left text-sm text-ink transition ${active ? "bg-blue-soft" : "hover:bg-canvas"}`}
                >
                  <Avatar name={p.name} personaId={p.id} size={34} />
                  <span className="min-w-0 flex-1">
                    <span className="block">{p.name}</span>{" "}
                    <small className="block text-xs text-muted">{p.title}</small>{" "}
                    <small className="block text-xs text-muted">Reads {p.can_read_docs} of {p.total_docs} documents</small>
                  </span>
                  {active && <TickCircleIcon size={18} className="shrink-0 text-blue" />}
                </button>
              );
            })}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
