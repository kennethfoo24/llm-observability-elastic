import { motion } from "motion/react";
import { STAGE_HINTS } from "../../lib/copy";
import { formatMs } from "../../lib/format";
import { layoutStages } from "../../lib/stages";
import type { Stage, Verdict } from "../../lib/types";

export function Waterfall({ stages, verdict }: { stages: Stage[]; verdict: Verdict }) {
  const rows = layoutStages(stages);
  if (rows.length === 0) return <p className="text-sm text-on-ink-muted">No timing data</p>;
  return (
    <ol className="grid gap-3">
      {rows.map((row, i) => {
        const color = row.name === "guardrail.check" ? (verdict === "FLAGGED" ? "bg-flag" : "bg-clean") : row.name === "llm.generate" ? "bg-cost" : "bg-blue-bright";
        return (
          <li key={`${row.name}-${i}`} title={STAGE_HINTS[row.name]} className="min-w-0">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 break-words">{row.label}</span>
              <span className="num shrink-0 text-on-ink-muted">{formatMs(row.ms)}</span>
            </div>
            <div className="relative mt-1.5 h-2 w-full overflow-hidden" aria-hidden>
              <motion.span
                className={`absolute top-0 h-2 rounded-full ${color}`}
                style={{ left: `${row.offsetPct}%`, width: `${row.widthPct}%`, transformOrigin: "left" }}
                initial={{ scaleX: 0, opacity: 0.4 }} animate={{ scaleX: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 140, damping: 20, delay: i * 0.06 }}
              />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
