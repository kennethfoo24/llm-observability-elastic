import { ArrowCounterClockwise, Coins } from "@phosphor-icons/react";
import { formatCost } from "../lib/format";

export function Header({ spendUsd, onReset, canReset }: { spendUsd: number; onReset: () => void; canReset: boolean }) {
  return (
    <header className="flex h-16 items-center justify-between border-b border-line bg-surface px-4 md:px-6">
      <div className="flex items-baseline gap-3">
        <span className="whitespace-nowrap text-lg font-semibold tracking-tight text-ink">Nimbus Corp</span>
        <span className="hidden text-sm text-muted sm:inline">HR Assistant</span>
      </div>
      <div className="flex items-center gap-3 sm:gap-4">
        <div className="flex items-center gap-2 whitespace-nowrap text-sm text-muted" title="Total model cost of this conversation">
          <Coins size={18} weight="regular" aria-hidden />
          <span className="sr-only sm:not-sr-only">Session cost</span>
          <span className="num font-bold text-ink">{formatCost(spendUsd)}</span>
        </div>
        <button
          type="button" onClick={onReset} disabled={!canReset}
          className="flex items-center gap-2 whitespace-nowrap rounded-control border border-line px-3 py-2 text-sm font-medium text-ink transition hover:bg-canvas active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ArrowCounterClockwise size={16} weight="regular" aria-hidden />
          <span className="sr-only sm:not-sr-only">New conversation</span>
        </button>
      </div>
    </header>
  );
}
