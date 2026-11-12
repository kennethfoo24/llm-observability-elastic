import { useEffect, useRef, type ReactNode } from "react";
import { CloseCircleIcon } from "./icons";
import { MeshBackground } from "./MeshBackground";
import { useMediaQuery } from "../hooks/useMediaQuery";

type Slots = {
  sidebar: ReactNode; thread: ReactNode; composer: ReactNode; cost: ReactNode; menuButton: ReactNode; drawer: ReactNode; tab: ReactNode;
  sidebarOpen: boolean; onSidebarClose: () => void;
};

/* A rounded frame floating on the page colour, with the drifting mesh behind it. 64rem and wider: sidebar inline (300px) beside the chat.
   Narrower: the sidebar is a modal off-canvas dialog opened from a menu button, and below 48rem the frame goes edge to edge.
   The View More tab and the drawer live inside the frame so they position against its right edge. */
export function AppShell({ sidebar, thread, composer, cost, menuButton, drawer, tab, sidebarOpen, onSidebarClose }: Slots) {
  const lgUp = useMediaQuery("(min-width: 64rem)");
  const open = sidebarOpen && !lgUp;
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onSidebarClose);
  onCloseRef.current = onSidebarClose;

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { if (!e.defaultPrevented) onCloseRef.current(); return; }
      if (e.key !== "Tab") return;
      // keep Tab inside the dialog: aria-modal says the page behind is inert
      const nodes = Array.from(panel.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? []);
      if (nodes.length === 0) return e.preventDefault();
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement;
      const inside = panel.current?.contains(active) ?? false;
      if (!inside || (!e.shiftKey && active === last)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && (active === first || active === panel.current)) { e.preventDefault(); last.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      opener.current?.focus();
    };
  }, [open]);

  return (
    <div className="min-h-[100dvh] md:p-6">
      <div className="relative isolate mx-auto grid h-[100dvh] w-full grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)] overflow-hidden md:h-[calc(100dvh-3rem)] md:gap-4 md:rounded-[32px] md:p-4 lg:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[340px_minmax(0,1fr)]">
        <MeshBackground />
        {lgUp && <div className="min-h-0">{sidebar}</div>}
        <main aria-label="Chat" className="relative flex min-h-0 min-w-0 flex-col">
          <div className="flex items-center justify-between px-4 pt-3 md:px-7 md:pt-2">
            <div>{!lgUp && menuButton}</div>
            {cost}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{thread}</div>
          <div className="pointer-events-none absolute inset-x-0 bottom-3 md:bottom-5"><div className="pointer-events-auto">{composer}</div></div>
        </main>
        {open && (
          <>
            <div data-testid="sidebar-scrim" className="fixed inset-0 z-40 bg-ink/50" onClick={onSidebarClose} aria-hidden />
            <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Conversation history" className="fixed inset-y-0 left-0 z-50 w-[min(320px,88vw)] p-3 outline-none">
              {sidebar}
              <button type="button" onClick={onSidebarClose} aria-label="Close conversations" className="absolute right-6 top-6 grid size-9 place-items-center rounded-full bg-canvas text-ink transition hover:bg-line focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue">
                <CloseCircleIcon size={20} />
              </button>
            </div>
          </>
        )}
        {tab}
        {drawer}
      </div>
    </div>
  );
}
