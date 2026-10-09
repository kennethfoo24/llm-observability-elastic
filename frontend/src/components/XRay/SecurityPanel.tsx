import { OUTPUT_FINDINGS, reasonLabel } from "../../lib/copy";
import { alertsUrl, owaspDashboardUrl, responseLogUrl, traceUrl } from "../../lib/kibanaLinks";
import { FindingPills, type Pill } from "./FindingPills";
import { ExtLink } from "./ExtLink";
import type { ChatResponse, Findings } from "../../lib/types";

/** Security findings only: what the guardrail caught in the prompt, and what the output checks caught in the answer. */
export function SecurityPanel({ r, findings, kibanaUrl, securityKibanaUrl }: { r: ChatResponse; findings: Findings; kibanaUrl?: string; securityKibanaUrl?: string | null }) {
  const inputLink = securityKibanaUrl && (r.blocked || r.guardrail.verdict === "FLAGGED") ? alertsUrl(securityKibanaUrl) : kibanaUrl && r.trace_id ? traceUrl(kibanaUrl, r.trace_id) : undefined;
  const pills: Pill[] = [
    ...r.guardrail.reasons.map((x) => ({ key: `in-${x}`, label: reasonLabel(x), tag: "Prompt", href: inputLink })),
    ...findings.security.map((x) => ({ key: `out-${x}`, label: OUTPUT_FINDINGS[x]?.label ?? x.replace(/_/g, " "), tag: OUTPUT_FINDINGS[x]?.owasp ?? "Answer", href: kibanaUrl && r.trace_id ? responseLogUrl(kibanaUrl, r.trace_id) : undefined })),
  ];
  const scoring = !r.blocked && findings.status === "pending";
  return (
    <div className="min-w-0">
      {pills.length > 0 ? <FindingPills pills={pills} tone="flag" label="Security findings" /> : !scoring && <p className="text-sm text-on-ink-muted">No security findings.</p>}
      {scoring && <p role="status" className="mt-2 text-xs text-on-ink-muted">Elastic is still scoring the answer, so output checks may add findings in a few seconds.</p>}
      {findings.status === "unavailable" && !r.blocked && <p className="mt-2 text-xs text-on-ink-muted">Output checks could not be read back. Open the response log in Kibana.</p>}
      {kibanaUrl && <div className="mt-3 flex flex-wrap gap-2"><ExtLink href={owaspDashboardUrl(kibanaUrl)}>OWASP coverage dashboard</ExtLink></div>}
    </div>
  );
}
