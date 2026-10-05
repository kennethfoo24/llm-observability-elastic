import { motion } from "motion/react";
import { Eye } from "@phosphor-icons/react";
import { AnswerText } from "./AnswerText";
import { BlockCard, DegradedNote, ErrorCard, FlagNote } from "./InlineNotices";
import { formatCost, formatMs } from "../lib/format";
import type { AssistantMsg } from "../state/chatState";

type Props = {
  msg: AssistantMsg; selected: boolean; personaName: string;
  onSelect: (id: string) => void; onCitation: (docId: string, msgId: string) => void; onRetry: (id: string) => void;
};

export function AssistantMessage({ msg, selected, personaName, onSelect, onCitation, onRetry }: Props) {
  const r = msg.response;
  const total = r ? r.stages.reduce((a, s) => a + s.ms, 0) : 0;

  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 140, damping: 20 }}
      className={`min-w-0 border-l-2 pl-4 ${selected ? "border-blue" : "border-transparent"}`}
      aria-label={`Answer for ${personaName}`}
    >
      <p className="mb-1 text-xs font-medium text-muted">Asked as {personaName}</p>

      {msg.status === "pending" && (
        <div role="status" aria-busy="true" aria-label="Waiting for the answer" className="grid max-w-prose gap-2 py-1">
          <div className="h-3.5 w-11/12 animate-pulse rounded-full bg-line" />
          <div className="h-3.5 w-9/12 animate-pulse rounded-full bg-line" />
          <div className="h-3.5 w-6/12 animate-pulse rounded-full bg-line" />
        </div>
      )}

      {msg.status === "error" && <ErrorCard error={msg.error ?? { status: 0, code: "unknown" }} onRetry={() => onRetry(msg.id)} />}

      {msg.status === "done" && r && (
        <>
          {r.blocked ? (
            <BlockCard reasons={r.block_reason} />
          ) : r.answer.trim() ? (
            <AnswerText text={r.answer} knownIds={new Set(r.docs.map((d) => d.id))} onCitation={(docId) => onCitation(docId, msg.id)} />
          ) : (
            <p className="text-muted">No answer was returned. Try rephrasing the question.</p>
          )}
          {!r.blocked && r.guardrail.verdict === "FLAGGED" && <FlagNote reasons={r.guardrail.reasons} />}
          {r.guardrail.status === "degraded" && <DegradedNote />}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
            <span>{r.docs.length} {r.docs.length === 1 ? "source" : "sources"}</span>
            <span className="num">{formatMs(total)}</span>
            <span className="num">{formatCost(r.cost_usd)}</span>
            <button
              type="button" onClick={() => onSelect(msg.id)} aria-pressed={selected}
              className="ml-auto flex items-center gap-1.5 rounded-control px-2 py-1 font-medium text-blue transition hover:bg-blue-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue aria-pressed:bg-blue-soft"
            >
              <Eye size={16} aria-hidden /> Inspect
            </button>
          </div>
        </>
      )}
    </motion.article>
  );
}
