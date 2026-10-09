import { QUALITY_FINDINGS, QUALITY_HELP } from "../../lib/copy";
import { qualityDashboardUrl, qualityDevToolsUrl, responseLogUrl } from "../../lib/kibanaLinks";
import { isAnswered, qualityInput } from "../../lib/quality";
import { FindingPills, type Pill } from "./FindingPills";
import { ExtLink } from "./ExtLink";
import type { ChatResponse, Findings } from "../../lib/types";

/** Conversation-quality findings only. Failure to answer is known at once in the browser; the rest arrive from Elastic's scoring. */
export function QualityPanel({ r, findings, kibanaUrl, prompt, qualityPipeline }: { r: ChatResponse; findings: Findings; kibanaUrl?: string; prompt?: string; qualityPipeline?: string }) {
  const devTools = kibanaUrl && prompt && qualityPipeline ? qualityDevToolsUrl(kibanaUrl, qualityInput(r, prompt), qualityPipeline) : null;
  const keys = new Set(findings.quality);
  if (!r.blocked && !isAnswered(r.answer)) keys.add("not_answered");
  const href = kibanaUrl && r.trace_id ? responseLogUrl(kibanaUrl, r.trace_id) : undefined;
  const pills: Pill[] = [...keys].map((k) => ({ key: k, label: QUALITY_FINDINGS[k]?.label ?? k.replace(/_/g, " "), tag: QUALITY_FINDINGS[k]?.owasp, href }));
  const scoring = !r.blocked && findings.status === "pending";
  return (
    <div className="min-w-0">
      {r.blocked ? <p className="text-sm text-on-ink-muted">Blocked before an answer existed, so there is nothing to score.</p>
        : pills.length > 0 ? <FindingPills pills={pills} tone="warn" label="Quality findings" />
        : !scoring && <p className="text-sm text-on-ink-muted">No quality findings.</p>}
      {scoring && <p role="status" className="mt-2 text-xs text-on-ink-muted">Elastic scores each answer about 5 to 10 seconds after it is shown; findings appear here when it is done.</p>}
      {kibanaUrl && (
        <div className="mt-3 flex flex-wrap gap-2">
          {devTools && <ExtLink href={devTools}>Try it in Dev Tools</ExtLink>}
          {r.trace_id && <ExtLink href={responseLogUrl(kibanaUrl, r.trace_id)}>Open the response log</ExtLink>}
          <ExtLink href={qualityDashboardUrl(kibanaUrl)}>Conversation quality dashboard</ExtLink>
        </div>
      )}
      {kibanaUrl && <p className="mt-3 text-xs text-on-ink-muted">{QUALITY_HELP}</p>}
    </div>
  );
}
