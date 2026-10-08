import { CHECKS_TITLE, QUALITY_CHECKS, QUALITY_HELP, QUALITY_TIMING } from "../../lib/copy";
import { owaspDashboardUrl, qualityDashboardUrl, qualityDevToolsUrl, responseLogUrl } from "../../lib/kibanaLinks";
import { qualityInput } from "../../lib/quality";
import { ExtLink } from "./ExtLink";

const ROW_LINK = "text-xs font-medium underline underline-offset-2 rounded-sm transition hover:text-blue-bright focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-bright";
import type { ChatResponse } from "../../lib/types";

export function QualityPanel({ r, kibanaUrl, prompt, qualityPipeline }: { r: ChatResponse; kibanaUrl?: string; prompt?: string; qualityPipeline?: string }) {
  const devTools = kibanaUrl && prompt && qualityPipeline ? qualityDevToolsUrl(kibanaUrl, qualityInput(r, prompt), qualityPipeline) : null;
  return (
    <div className="min-w-0">
      <p className="text-sm text-on-ink-muted">{QUALITY_TIMING}</p>
      <h4 className="mt-3 text-sm font-semibold">{CHECKS_TITLE}</h4>
      <ul aria-label={CHECKS_TITLE} className="mt-2 grid gap-2">
        {QUALITY_CHECKS.map((c) => (
          <li key={c.key} className="min-w-0 rounded-control bg-ink-3 px-3 py-2 text-sm">
            <p className="flex flex-wrap items-baseline gap-x-2">
              {c.owaspUrl
                ? <ExtLink href={c.owaspUrl} icon={false} className={ROW_LINK}><span className="num font-bold">{c.id}</span></ExtLink>
                : <span className="num font-bold text-on-ink-muted">{c.id}</span>}
              <span className="min-w-0 break-words font-medium">{c.name}</span>
            </p>
            <p className="mt-1 break-words text-xs text-on-ink-muted">{c.what}</p>
            {kibanaUrl && (
              <p className="mt-1">
                <ExtLink href={c.dashboard === "owasp" ? owaspDashboardUrl(kibanaUrl) : qualityDashboardUrl(kibanaUrl)} icon={false} className={ROW_LINK}>
                  See it in Kibana
                </ExtLink>
              </p>
            )}
          </li>
        ))}
      </ul>
      {kibanaUrl && (
        <div className="mt-4 flex flex-wrap gap-2">
          {devTools && <ExtLink href={devTools}>Try it in Dev Tools</ExtLink>}
          {r.trace_id && <ExtLink href={responseLogUrl(kibanaUrl, r.trace_id)}>Open the response log</ExtLink>}
          <ExtLink href={qualityDashboardUrl(kibanaUrl)}>Conversation quality dashboard</ExtLink>
          <ExtLink href={owaspDashboardUrl(kibanaUrl)}>OWASP coverage dashboard</ExtLink>
        </div>
      )}
      {kibanaUrl && <p className="mt-3 text-xs text-on-ink-muted">{QUALITY_HELP}</p>}
    </div>
  );
}
