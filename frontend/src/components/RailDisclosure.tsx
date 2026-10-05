import { useId, useState } from "react";
import { CaretDown } from "@phosphor-icons/react";

/* Below lg the person and model controls collapse behind a summary row so the chat stays on the first screen; at lg they are always visible. */
export function RailDisclosure({ persona, model, children }: { persona: string; model: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div>
      <div className="flex items-center justify-between gap-3 px-4 py-2 lg:hidden">
        <p className="min-w-0 truncate text-sm text-muted">
          Asking as <span className="font-medium text-ink">{persona}</span>, {model}
        </p>
        <button
          type="button" aria-label="Change person or model" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((o) => !o)}
          className="flex shrink-0 items-center gap-1.5 rounded-control border border-field px-3 py-1.5 text-sm font-medium text-ink transition hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
        >
          Change
          <CaretDown size={14} aria-hidden className={open ? "rotate-180" : ""} />
        </button>
      </div>
      <div id={panelId} className={open ? "max-h-[55dvh] overflow-y-auto border-t border-line lg:max-h-none lg:border-t-0" : "hidden lg:block"}>
        {children}
      </div>
    </div>
  );
}
