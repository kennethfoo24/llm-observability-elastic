import type { ReactNode } from "react";
import { XRaySheet } from "./XRaySheet";

type Slots = { header: ReactNode; rail: ReactNode; thread: ReactNode; composer: ReactNode; xray: ReactNode; xrayOpen: boolean; onXrayClose: () => void };

/* Desktop (lg): rail 300px | chat | x-ray 420px. Below lg: one full-height column (rail summary row, chat, composer); the x-ray is a bottom sheet. */
export function AppShell({ header, rail, thread, composer, xray, xrayOpen, onXrayClose }: Slots) {
  return (
    <div className="grid h-[100dvh] grid-rows-[auto_minmax(0,1fr)]">
      {header}
      <div className="grid min-h-0 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-rows-1 lg:grid-cols-[300px_minmax(0,1fr)_420px]">
        <aside className="border-b border-line bg-surface lg:min-h-0 lg:overflow-y-auto lg:border-b-0 lg:border-r">{rail}</aside>
        <main className="grid min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto] lg:min-h-0">
          <div className="min-h-0 overflow-y-auto">{thread}</div>
          <div className="border-t border-line bg-surface pb-[env(safe-area-inset-bottom)]">{composer}</div>
        </main>
        <section className="on-ink hidden min-h-0 bg-ink text-on-ink lg:block lg:overflow-y-auto" aria-label="X-ray">{xray}</section>
      </div>
      <XRaySheet open={xrayOpen} onClose={onXrayClose}>{xray}</XRaySheet>
    </div>
  );
}
