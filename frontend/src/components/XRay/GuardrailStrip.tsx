import { ShieldCheck, ShieldWarning, ShieldSlash } from "@phosphor-icons/react";
import { reasonLabel } from "../../lib/copy";
import { formatMs } from "../../lib/format";
import type { ChatResponse } from "../../lib/types";

export function GuardrailStrip({ r }: { r: ChatResponse }) {
  const g = r.guardrail;
  const flagged = g.verdict === "FLAGGED";
  const scored = typeof g.injection_score === "number" && Number.isFinite(g.injection_score);
  // an unscored non-flagged verdict is not "Clean": only the regex checks ran
  const patternsOnly = !flagged && !scored;
  const Icon = r.blocked || flagged ? ShieldWarning : patternsOnly || g.verdict === "UNKNOWN" ? ShieldSlash : ShieldCheck;
  const word = r.blocked ? "Blocked" : flagged ? "Flagged" : patternsOnly ? "Patterns only" : g.verdict === "UNKNOWN" ? "Unscored" : "Clean";
  const tone = r.blocked || flagged ? "text-flag" : patternsOnly || g.verdict === "UNKNOWN" ? "text-on-ink-muted" : "text-clean";
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <span className={`flex items-center gap-2 text-lg font-semibold ${tone}`}><Icon size={22} weight="regular" aria-hidden /> {word}</span>
        {g.status === "degraded" && <span className="rounded-full border border-ink-line px-2 py-0.5 text-xs font-medium text-on-ink-muted">Degraded</span>}
        <span className="num ml-auto text-xs text-on-ink-muted">{formatMs(g.latency_ms)}</span>
      </div>
      {g.reasons.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {g.reasons.map((x) => <li key={x} className="min-w-0 break-words rounded-full bg-ink-3 px-3 py-1 text-sm">{reasonLabel(x)}</li>)}
        </ul>
      )}
      <dl className="mt-3 flex items-baseline justify-between gap-3 text-sm">
        <dt className="text-on-ink-muted">Injection probability</dt>
        <dd className="num font-bold">{scored ? g.injection_score!.toFixed(2) : "n/a"}</dd>
      </dl>
      {patternsOnly && <p className="mt-3 text-sm text-on-ink-muted">The injection model did not answer, so only pattern checks ran.</p>}
      {r.blocked && <p className="mt-3 text-sm text-on-ink-muted">Stopped before any search or model call, so nothing was retrieved or billed.</p>}
    </div>
  );
}
