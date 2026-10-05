import type { ReactNode } from "react";

type Slots = { header: ReactNode; rail: ReactNode; thread: ReactNode; composer: ReactNode; xray: ReactNode };

/* Desktop (lg): rail 300px | chat | x-ray 420px. Below lg: one column; the x-ray is a bottom sheet owned by the caller. */
export function AppShell({ header, rail, thread, composer, xray }: Slots) {
  return (
    <div className="grid min-h-[100dvh] grid-rows-[auto_minmax(0,1fr)] lg:h-[100dvh]">
      {header}
      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_420px]">
        <aside className="border-b border-line bg-surface lg:min-h-0 lg:overflow-y-auto lg:border-b-0 lg:border-r">{rail}</aside>
        <main className="grid min-h-[60dvh] min-w-0 grid-rows-[minmax(0,1fr)_auto] lg:min-h-0">
          <div className="min-h-0 overflow-y-auto">{thread}</div>
          <div className="border-t border-line bg-surface">{composer}</div>
        </main>
        <section className="on-ink min-h-0 bg-ink text-on-ink lg:overflow-y-auto" aria-label="X-ray">{xray}</section>
      </div>
    </div>
  );
}
