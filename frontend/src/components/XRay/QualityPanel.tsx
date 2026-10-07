import { OWASP_CHIPS, QUALITY_CHIP, QUALITY_HELP, QUALITY_TIMING } from "../../lib/copy";
import { owaspDashboardUrl, qualityDashboardUrl, qualityDevToolsUrl, responseLogUrl } from "../../lib/kibanaLinks";
import { qualityInput } from "../../lib/quality";
import { ExtLink } from "./ExtLink";
import type { ChatResponse } from "../../lib/types";

export function QualityPanel({ r, kibanaUrl, prompt, qualityPipeline }: { r: ChatResponse; kibanaUrl?: string; prompt?: string; qualityPipeline?: string }) {
  const devTools = kibanaUrl && prompt && qualityPipeline ? qualityDevToolsUrl(kibanaUrl, qualityInput(r, prompt), qualityPipeline) : null;
  return (
    <div className="min-w-0">
      <p className="text-sm text-on-ink-muted">{QUALITY_TIMING}</p>
      <ul aria-label="OWASP risks checked" className="mt-3 grid gap-2">
        {OWASP_CHIPS.map((c) => (
          <li key={c.id} className="min-w-0">
            <span className="inline-flex max-w-full flex-wrap items-baseline gap-x-2 rounded-2xl bg-ink-3 px-3 py-1 text-sm">
              <span className="num font-bold">{c.id}</span><span className="min-w-0 break-words">{c.name}</span>
            </span>
            <span className="mt-1 block pl-1 text-xs text-on-ink-muted">{c.detail}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3"><span className="inline-block max-w-full break-words rounded-2xl bg-ink-3 px-3 py-1 text-sm">{QUALITY_CHIP}</span></p>
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
