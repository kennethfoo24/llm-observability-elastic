import { useId } from "react";
import { motion } from "motion/react";
import { ExtLink } from "./ExtLink";
import { costDashboardUrl, devToolsUrl, owaspDashboardUrl, qualityDashboardUrl, qualityDevToolsUrl, responseLogUrl, traceUrl } from "../../lib/kibanaLinks";
import { DEVTOOLS_HELP, QUALITY_HELP } from "../../lib/copy";
import { qualityInput } from "../../lib/quality";
import { ExternalIcon } from "../icons";
import { CostPanel } from "./CostPanel";
import { GuardrailStrip } from "./GuardrailStrip";
import { QualityPanel } from "./QualityPanel";
import { SecurityPanel } from "./SecurityPanel";
import { useFindings } from "../../hooks/useFindings";
import { Retrieval } from "./Retrieval";
import { Waterfall } from "./Waterfall";
import type { AssistantMsg } from "../../state/chatState";
import type { Persona } from "../../lib/types";
import type { GuardrailConfig } from "../../lib/kibanaLinks";

type Props = { msg: AssistantMsg | null; persona: Persona | undefined; question: string | undefined; kibanaUrl: string | undefined; securityKibanaUrl?: string | null; guardrailConfig?: GuardrailConfig; qualityPipeline?: string; highlightDocId: string | null };

type Link = { label: string; href: string };

/* The title can itself be a link (Dev Tools, with the hint as its tooltip); `actions` are the small links stacked on the right. */
function Section({ title, titleLink, actions, children }: { title: string; titleLink?: { href: string; hint: string }; actions?: Link[]; children: React.ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="min-w-0 border-t border-ink-line px-5 py-5 first:border-t-0">
      <div className="mb-3 flex items-start justify-between gap-3">
        <h3 id={id} className="text-sm font-semibold">
          {titleLink ? (
            <a href={titleLink.href} target="_blank" rel="noreferrer noopener" title={`${titleLink.hint} Opens in a new tab.`} className="inline-flex items-center gap-1.5 underline decoration-ink-line decoration-dotted underline-offset-4 hover:decoration-current">
              {title}<ExternalIcon size={13} />
            </a>
          ) : title}
        </h3>
        {actions && actions.length > 0 && (
          <div className="flex flex-col items-end gap-1">
            {actions.map((a) => <ExtLink key={a.label} href={a.href} icon={false} className="text-xs font-medium text-blue-bright hover:underline">{a.label} ↗</ExtLink>)}
          </div>
        )}
      </div>
      {children}
    </section>
  );
}

function Skeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Collecting the trace" className="grid gap-4 px-5 py-5">
      {["Guardrail check", "Hybrid search", "Prompt build", "LLM call"].map((s) => (
        <div key={s}><div className="h-3 w-32 animate-pulse motion-reduce:animate-none rounded-full bg-ink-3" /><div className="mt-2 h-2 w-full animate-pulse motion-reduce:animate-none rounded-full bg-ink-2" /></div>
      ))}
    </div>
  );
}

export function XRayDrawer({ msg, persona, question, kibanaUrl, securityKibanaUrl, guardrailConfig, qualityPipeline, highlightDocId }: Props) {
  const r = msg?.response;
  const guardrailDevTools = r && kibanaUrl && question && guardrailConfig ? devToolsUrl(kibanaUrl, question, guardrailConfig) : null;
  const qualityDevTools = r && kibanaUrl && question && qualityPipeline ? qualityDevToolsUrl(kibanaUrl, qualityInput(r, question), qualityPipeline) : null;
  const findings = useFindings(r?.trace_id, msg?.status === "done" && !!r && !r.blocked);
  return (
    <div className="min-w-0 pb-8">
      <div className="px-5 pb-4 pt-5 pr-14">
        <h2 className="text-lg font-semibold">LLM Observability</h2>
      </div>

      {!msg && (
        <>
          <p className="px-5 text-sm text-on-ink-muted">Send a question to see what Elastic recorded for it.</p>
          <div aria-hidden className="grid gap-4 px-5 py-5 opacity-60">
            {["Guardrail check", "Hybrid search", "Prompt build", "LLM call"].map((s) => (
              <div key={s}><div className="h-3 w-32 rounded-full bg-ink-3" /><div className="mt-2 h-2 w-full rounded-full bg-ink-2" /></div>
            ))}
          </div>
        </>
      )}
      {msg?.status === "pending" && <Skeleton />}
      {msg?.status === "error" && <p className="px-5 text-sm text-on-ink-muted">No trace for a failed request.</p>}

      {msg?.status === "done" && r && (
        <motion.div key={msg.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 140, damping: 20 }}>
          <Section title="Guardrail" titleLink={guardrailDevTools ? { href: guardrailDevTools, hint: DEVTOOLS_HELP } : undefined}><GuardrailStrip r={r} kibanaUrl={kibanaUrl} securityKibanaUrl={securityKibanaUrl} /></Section>
          <Section title="Security" actions={kibanaUrl ? [{ label: "OWASP Top 10 dashboard", href: owaspDashboardUrl(kibanaUrl) }] : undefined}><SecurityPanel r={r} findings={findings} kibanaUrl={kibanaUrl} securityKibanaUrl={securityKibanaUrl} /></Section>
          <Section
            title="Quality" titleLink={qualityDevTools ? { href: qualityDevTools, hint: QUALITY_HELP } : undefined}
            actions={kibanaUrl ? [{ label: "Quality dashboard", href: qualityDashboardUrl(kibanaUrl) }, ...(r.trace_id ? [{ label: "Log", href: responseLogUrl(kibanaUrl, r.trace_id) }] : [])] : undefined}
          ><QualityPanel r={r} findings={findings} kibanaUrl={kibanaUrl} /></Section>
          <Section title="Trace" actions={kibanaUrl && r.trace_id ? [{ label: "Trace", href: traceUrl(kibanaUrl, r.trace_id) }] : undefined}>
            <Waterfall stages={r.stages} verdict={r.guardrail.verdict} scored={r.guardrail.injection_score !== null} />
            {!(kibanaUrl && r.trace_id) && <p className="mt-4 text-xs text-on-ink-muted">Trace link unavailable</p>}
          </Section>
          <Section title="Retrieval">
            <Retrieval docs={r.docs} hidden={r.hidden} personaName={persona?.name ?? "this person"} highlightDocId={highlightDocId} kibanaUrl={kibanaUrl} />
          </Section>
          <Section title="Cost" actions={kibanaUrl ? [{ label: "Cost", href: costDashboardUrl(kibanaUrl) }] : undefined}><CostPanel r={r} /></Section>
        </motion.div>
      )}
    </div>
  );
}
