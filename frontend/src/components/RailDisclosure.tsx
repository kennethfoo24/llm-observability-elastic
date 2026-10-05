import { useCallback, useEffect, useId, useRef, useState } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { useMediaQuery } from "../hooks/useMediaQuery";

type Api = { closeAfterPick: () => void };

/* Below lg the person and model controls collapse behind a summary row so the chat stays on the first screen; at lg they are always visible.
   The open panel is height capped (the composer must stay visible on a short phone), scrolls inside, and shows a bottom fade while there is more below. */
export function RailDisclosure({ persona, model, children }: { persona: string; model: string; children: React.ReactNode | ((api: Api) => React.ReactNode) }) {
  const [open, setOpen] = useState(false);
  const [moreBelow, setMoreBelow] = useState(false);
  const panelId = useId();
  const toggle = useRef<HTMLButtonElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const wide = useMediaQuery("(min-width: 64rem)");

  const measure = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    setMoreBelow(el.scrollHeight - el.clientHeight - el.scrollTop > 2);
  }, []);
  useEffect(() => {
    if (!open) return;
    measure();
    const el = scroller.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [open, measure]);

  // picking a model is a decision: collapse so the chat returns to view (a persona pick keeps the panel open)
  const closeAfterPick = useCallback(() => {
    if (wide) return;
    setOpen(false);
    toggle.current?.focus();
  }, [wide]);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 px-4 py-2 lg:hidden">
        <p className="min-w-0 truncate text-sm text-muted">
          Asking as <span className="font-medium text-ink">{persona}</span>, {model}
        </p>
        <button
          ref={toggle} type="button" aria-label="Change person or model" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((o) => !o)}
          className="flex shrink-0 items-center gap-1.5 rounded-control border border-field px-3 py-1.5 text-sm font-medium text-ink transition hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
        >
          Change
          <CaretDown size={14} aria-hidden className={open ? "rotate-180" : ""} />
        </button>
      </div>
      <div id={panelId} className={open ? "relative border-t border-line lg:border-t-0" : "hidden lg:block"}>
        <div
          ref={scroller} data-testid="rail-scroll" onScroll={measure}
          className={open ? "max-h-[min(55dvh,calc(100dvh-18rem))] overflow-y-auto lg:max-h-none lg:overflow-visible" : ""}
        >
          {typeof children === "function" ? children({ closeAfterPick }) : children}
        </div>
        {open && moreBelow && (
          <div data-testid="rail-scroll-cue" aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-surface to-transparent lg:hidden" />
        )}
      </div>
    </div>
  );
}
