import { useEffect, useRef, type ReactNode } from "react";
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
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCloseRef.current(); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener.current?.focus();
    };
  }, [open]);

  return (
    <div className="min-h-[100dvh] md:p-6">
      <div className="relative isolate mx-auto grid h-[100dvh] max-w-[1440px] grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)] overflow-hidden md:h-[calc(100dvh-3rem)] md:gap-4 md:rounded-[32px] md:p-4 lg:grid-cols-[300px_minmax(0,1fr)]">
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
            </div>
          </>
        )}
        {tab}
        {drawer}
      </div>
    </div>
  );
}
