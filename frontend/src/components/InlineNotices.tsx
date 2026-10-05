import { ArrowClockwise, Flag, ShieldWarning, WarningCircle } from "@phosphor-icons/react";
import { reasonLabel } from "../lib/copy";

export function BlockCard({ reasons }: { reasons: string[] }) {
  return (
    <div className="rounded-card border border-flag/40 bg-flag-soft p-4 text-flag-ink">
      <h3 className="flex items-center gap-2 font-semibold"><ShieldWarning size={20} weight="regular" aria-hidden /> Blocked by the guardrail</h3>
      <p className="mt-1 text-sm">This question was stopped before any document search or model call. Detected:</p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {reasons.map((r) => <li key={r} className="rounded-full bg-white/70 px-3 py-1 text-sm font-medium">{reasonLabel(r)}</li>)}
      </ul>
    </div>
  );
}

export function FlagNote({ reasons }: { reasons: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-control bg-flag-soft px-3 py-2 text-sm text-flag-ink">
      <Flag size={16} aria-hidden /> <span className="font-medium">Flagged for review</span>
      {reasons.map((r) => <span key={r} className="rounded-full bg-white/70 px-2 py-0.5">{reasonLabel(r)}</span>)}
    </div>
  );
}

export function DegradedNote() {
  return (
    <p className="mt-3 flex items-center gap-2 rounded-control bg-canvas px-3 py-2 text-sm text-muted">
      <WarningCircle size={16} aria-hidden /> The guardrail models were slow or unavailable, so only pattern checks ran.
    </p>
  );
}

const ERROR_COPY: Record<string, string> = {
  gemma_offline: "The self-hosted Gemma model is offline.",
  upstream_error: "The model service had a problem. Try again.",
  network_error: "Could not reach the server.",
  timeout: "The request took too long. Try again.",
  pricing_unavailable: "This model is not priced yet.",
  invalid_request: "That question could not be sent.",
  rate_limited: "Too many requests. Wait a moment and try again.",
};

export function errorMessage(code: string, status: number): string {
  return ERROR_COPY[code] ?? (status >= 500 ? ERROR_COPY.upstream_error : "Something went wrong.");
}

const BUTTON = "mt-3 flex items-center gap-2 rounded-control px-3 py-1.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue";

export function ErrorCard({ error, onRetry, alternative }: {
  error: { status: number; code: string; hint?: string }; onRetry: () => void; alternative?: { label: string; onUse: () => void };
}) {
  return (
    <div role="alert" className="rounded-card border border-line bg-surface p-4">
      <p className="flex items-center gap-2 font-medium text-ink"><WarningCircle size={20} className="text-flag-ink" aria-hidden /> {errorMessage(error.code, error.status)}</p>
      {error.hint && <p className="mt-1 text-sm text-muted">{error.hint}</p>}
      {alternative ? (
        <button type="button" onClick={alternative.onUse} className={`${BUTTON} bg-blue text-white hover:bg-blue-strong`}>
          <ArrowClockwise size={16} aria-hidden /> Try with {alternative.label}
        </button>
      ) : (
        <button type="button" onClick={onRetry} className={`${BUTTON} border border-line text-ink hover:bg-canvas`}>
          <ArrowClockwise size={16} aria-hidden /> Try again
        </button>
      )}
    </div>
  );
}
