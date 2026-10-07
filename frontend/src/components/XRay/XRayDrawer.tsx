import { useId } from "react";
import { motion } from "motion/react";
import { ExtLink } from "./ExtLink";
import { traceUrl } from "../../lib/kibanaLinks";
import { CostPanel } from "./CostPanel";
import { GuardrailStrip } from "./GuardrailStrip";
import { QualityPanel } from "./QualityPanel";
import { Retrieval } from "./Retrieval";
import { Waterfall } from "./Waterfall";
import type { AssistantMsg } from "../../state/chatState";
import type { Persona } from "../../lib/types";
import type { GuardrailConfig } from "../../lib/kibanaLinks";

type Props = { msg: AssistantMsg | null; persona: Persona | undefined; question: string | undefined; kibanaUrl: string | undefined; securityKibanaUrl?: string | null; guardrailConfig?: GuardrailConfig; qualityPipeline?: string; highlightDocId: string | null };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="min-w-0 border-t border-ink-line px-5 py-5 first:border-t-0">
      <h3 id={id} className="mb-3 text-sm font-semibold">{title}</h3>
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
  return (
    <div className="min-w-0 pb-8">
      <div className="px-5 pb-4 pt-5">
        <h2 className="text-lg font-semibold">LLM Observability</h2>
        <p className="mt-1 text-sm text-on-ink-muted">What Elastic recorded for this answer.</p>
        {question && <p className="mt-3 line-clamp-2 break-words rounded-control bg-ink-2 px-3 py-2 text-sm text-on-ink-muted">{question}</p>}
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
          <Section title="Guardrail"><GuardrailStrip r={r} kibanaUrl={kibanaUrl} securityKibanaUrl={securityKibanaUrl} prompt={question} guardrailConfig={guardrailConfig} /></Section>
          {!r.blocked && <Section title="Output guardrail and quality"><QualityPanel r={r} kibanaUrl={kibanaUrl} prompt={question} qualityPipeline={qualityPipeline} /></Section>}
          <Section title="Trace">
            <Waterfall stages={r.stages} verdict={r.guardrail.verdict} scored={r.guardrail.injection_score !== null} />
            {kibanaUrl && r.trace_id ? (
              <ExtLink href={traceUrl(kibanaUrl, r.trace_id)} className="mt-4 inline-flex items-center gap-2 rounded-control border border-ink-line px-3 py-2 text-sm font-medium transition hover:bg-ink-2">Open trace in Kibana</ExtLink>
            ) : (
              <p className="mt-4 text-xs text-on-ink-muted">Trace link unavailable</p>
            )}
          </Section>
          <Section title="Retrieval">
            <Retrieval docs={r.docs} hidden={r.hidden} personaName={persona?.name ?? "this person"} highlightDocId={highlightDocId} kibanaUrl={kibanaUrl} />
          </Section>
          <Section title="Model and cost"><CostPanel r={r} kibanaUrl={kibanaUrl} /></Section>
        </motion.div>
      )}
    </div>
  );
}
