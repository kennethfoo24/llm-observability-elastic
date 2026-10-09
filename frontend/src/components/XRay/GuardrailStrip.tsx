import { ShieldCheck, ShieldWarning, ShieldSlash } from "@phosphor-icons/react";
import { formatMs } from "../../lib/format";
import { alertsUrl, devToolsUrl, traceUrl, type GuardrailConfig } from "../../lib/kibanaLinks";
import { DETECTION_INTERVAL_MINUTES, DEVTOOLS_HELP } from "../../lib/copy";
import { ExtLink } from "./ExtLink";
import type { ChatResponse } from "../../lib/types";

export function GuardrailStrip({ r, kibanaUrl, securityKibanaUrl, prompt, guardrailConfig }: { r: ChatResponse; kibanaUrl?: string; securityKibanaUrl?: string | null; prompt?: string; guardrailConfig?: GuardrailConfig }) {
  const g = r.guardrail;
  const flagged = g.verdict === "FLAGGED";
  const scored = typeof g.injection_score === "number" && Number.isFinite(g.injection_score);
  // an unscored non-flagged verdict is not "Clean": only the regex checks ran
  const patternsOnly = !flagged && !scored;
  const Icon = r.blocked || flagged ? ShieldWarning : patternsOnly || g.verdict === "UNKNOWN" ? ShieldSlash : ShieldCheck;
  const word = r.blocked ? "Blocked" : flagged ? "Flagged" : patternsOnly ? "Patterns only" : g.verdict === "UNKNOWN" ? "Unscored" : "Clean";
  const tone = r.blocked || flagged ? "text-flag" : patternsOnly || g.verdict === "UNKNOWN" ? "text-on-ink-muted" : "text-clean";
  const devTools = kibanaUrl && prompt && guardrailConfig ? devToolsUrl(kibanaUrl, prompt, guardrailConfig) : null;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <span className={`flex items-center gap-2 text-lg font-semibold ${tone}`}><Icon size={22} weight="regular" aria-hidden /> {word}</span>
        {g.status === "degraded" && <span className="rounded-full border border-ink-line px-2 py-0.5 text-xs font-medium text-on-ink-muted">Degraded</span>}
        <span className="num ml-auto text-xs text-on-ink-muted">{formatMs(g.latency_ms)}</span>
      </div>
      <dl className="mt-3 flex items-baseline justify-between gap-3 text-sm">
        <dt className="text-on-ink-muted">Injection probability</dt>
        <dd className="num font-bold">{scored ? g.injection_score!.toFixed(2) : "n/a"}</dd>
      </dl>
      {patternsOnly && <p className="mt-3 text-sm text-on-ink-muted">The injection model did not answer, so only pattern checks ran.</p>}
      {r.blocked && <p className="mt-3 text-sm text-on-ink-muted">Stopped before any search or model call, so nothing was retrieved or billed.</p>}
      {(r.blocked || flagged) && (
        <div className="mt-3 grid gap-3">
          <p className="text-sm text-on-ink-muted">
            {r.blocked ? <>Blocked in <code className="num">guardrail.check</code> before retrieval and the LLM call.</> : <>Flagged in <code className="num">guardrail.check</code>.</>}
          </p>
          <div className="flex flex-wrap gap-2">
            {kibanaUrl && r.trace_id && <ExtLink href={traceUrl(kibanaUrl, r.trace_id)}>See where it was blocked</ExtLink>}
            {securityKibanaUrl && <ExtLink href={alertsUrl(securityKibanaUrl)}>View detection in Elastic Security</ExtLink>}
          </div>
          {securityKibanaUrl && (
            <p className="text-xs text-on-ink-muted">{`Detections run every ${DETECTION_INTERVAL_MINUTES === 1 ? "minute" : `${DETECTION_INTERVAL_MINUTES} minutes`}, so the alert can take a few minutes to appear.`}</p>
          )}
        </div>
      )}
      {devTools && (
        <div className="mt-3 grid gap-2">
          <div className="flex flex-wrap gap-2"><ExtLink href={devTools}>Try it in Dev Tools</ExtLink></div>
          <p className="text-xs text-on-ink-muted">{DEVTOOLS_HELP}</p>
        </div>
      )}
    </div>
  );
}
