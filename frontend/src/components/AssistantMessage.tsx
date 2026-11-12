import { motion } from "motion/react";
import { AnswerText } from "./AnswerText";
import { Avatar } from "./Avatar";
import { BlockCard, DegradedNote, ErrorCard, FlagNote } from "./InlineNotices";
import { RegenIcon, ShieldCrossIcon, TickCircleIcon } from "./icons";
import { reasonLabel } from "../lib/copy";
import { docDiscoverUrl } from "../lib/kibanaLinks";
import type { AssistantMsg } from "../state/chatState";
import type { ModelInfo, Persona } from "../lib/types";

type Props = {
  msg: AssistantMsg; models: ModelInfo[]; selected: boolean; personaName: string; persona?: Persona; otherPersona?: Persona;
  kibanaUrl?: string; pending: boolean;
  onSelect: (id: string) => void; onCitation: (docId: string, msgId: string) => void; onRetry: (id: string, modelKey?: string) => void;
  onAskAgain: (id: string) => void; onRegenerate: (id: string) => void; onOpenDetails: (id: string) => void;
};

const CHIP = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue hover:brightness-95";
const TONE = { ok: "bg-clean-soft text-clean-ink", bad: "bg-flag-soft text-flag-ink", neutral: "bg-[#e9edf5] text-[#4b5563]" } as const;
const PILL = "inline-flex items-center gap-2 rounded-full bg-white px-3.5 py-2 text-[13.5px] text-ink transition hover:shadow-[0_0_0_1px_#cfd6e4] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue";

export function AssistantMessage({ msg, models, selected, personaName, otherPersona, kibanaUrl, pending, onSelect, onCitation, onRetry, onAskAgain, onRegenerate, onOpenDetails }: Props) {
  const r = msg.response;
  // a failed message whose model is offline must not just retry that model: offer the first one that is up
  const failedModel = models.find((m) => m.key === msg.model);
  const alternative = failedModel && !failedModel.available ? models.find((m) => m.available) : undefined;
  const openDetails = () => { onSelect(msg.id); onOpenDetails(msg.id); };

  const chips: { key: string; tone: keyof typeof TONE; icon?: React.ReactNode; label: string }[] = [];
  if (r) {
    const reasons = (r.blocked ? r.block_reason : r.guardrail.reasons).map(reasonLabel).join(", ");
    if (r.blocked) chips.push({ key: "g", tone: "bad", icon: <ShieldCrossIcon size={13} />, label: `Blocked: ${reasons}` });
    else if (r.guardrail.verdict === "FLAGGED") chips.push({ key: "g", tone: "bad", icon: <ShieldCrossIcon size={13} />, label: `Flagged: ${reasons}` });
    else chips.push({ key: "g", tone: "ok", icon: <TickCircleIcon size={13} />, label: "Guardrail passed" });
    if (r.guardrail.status === "degraded") chips.push({ key: "d", tone: "neutral", label: "Checks degraded" });
    if (!r.blocked) chips.push({ key: "s", tone: "neutral", label: `${r.docs.length} ${r.docs.length === 1 ? "source" : "sources"}` });
    if (r.hidden.length > 0) chips.push({ key: "h", tone: "bad", icon: <ShieldCrossIcon size={13} />, label: `${r.hidden.length} ${r.hidden.length === 1 ? "document" : "documents"} hidden by access control` });
  }

  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 140, damping: 20 }}
      className={`min-w-0 border-l-2 pl-[36px] ${selected ? "border-blue/60" : "border-transparent"}`}
      aria-label={`Answer for ${personaName}`}
    >
      {msg.status === "pending" && (
        <div role="status" aria-busy="true" aria-label="Waiting for the answer" className="grid max-w-prose gap-2 py-1">
          <div className="h-3.5 w-11/12 animate-pulse motion-reduce:animate-none rounded-full bg-line" />
          <div className="h-3.5 w-9/12 animate-pulse motion-reduce:animate-none rounded-full bg-line" />
          <div className="h-3.5 w-6/12 animate-pulse motion-reduce:animate-none rounded-full bg-line" />
        </div>
      )}

      {msg.status === "error" && <ErrorCard error={msg.error ?? { status: 0, code: "unknown" }} alternative={alternative ? { label: alternative.label, onUse: () => onRetry(msg.id, alternative.key) } : undefined} onRetry={() => onRetry(msg.id)} />}

      {msg.status === "done" && r && (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <button key={c.key} type="button" onClick={openDetails} className={`${CHIP} ${TONE[c.tone]}`}>{c.icon}{c.label}</button>
            ))}
          </div>
          {r.blocked ? (
            <BlockCard reasons={r.block_reason} />
          ) : r.answer.trim() ? (
            <AnswerText
              text={r.answer} knownIds={new Set(r.docs.map((d) => d.id))} onCitation={(docId) => onCitation(docId, msg.id)}
              citation={{
                href: (id) => (kibanaUrl ? docDiscoverUrl(kibanaUrl, id) : undefined),
                titleOf: (id) => r.docs.find((d) => d.id === id)?.title ?? id,
                numberOf: (id) => r.docs.findIndex((d) => d.id === id) + 1,
              }}
            />
          ) : (
            <p className="text-muted">No answer was returned. Try rephrasing the question.</p>
          )}
          {!r.blocked && r.guardrail.verdict === "FLAGGED" && <FlagNote reasons={r.guardrail.reasons} />}
          {r.guardrail.status === "degraded" && <DegradedNote />}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {otherPersona && (
              <button type="button" disabled={pending} onClick={() => onAskAgain(msg.id)} aria-label={`Ask again as ${otherPersona.name}`} className={PILL}>
                <Avatar name={otherPersona.name} personaId={otherPersona.id} size={22} /> Ask again as {otherPersona.name}
              </button>
            )}
            <button type="button" disabled={pending} onClick={() => onRegenerate(msg.id)} className={PILL}>
              <RegenIcon size={16} /> Regenerate
            </button>
          </div>
        </>
      )}
    </motion.article>
  );
}
