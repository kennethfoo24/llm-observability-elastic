import { Lock } from "@phosphor-icons/react";
import { CLASSIFICATION_LABEL } from "../../lib/copy";
import { formatScore } from "../../lib/format";
import type { DocHit, Ghost } from "../../lib/types";

const chip = "shrink-0 rounded-full border border-ink-line px-2 py-0.5 text-xs text-on-ink-muted";

export function Retrieval({ docs, hidden, personaName, highlightDocId }: { docs: DocHit[]; hidden: Ghost[]; personaName: string; highlightDocId: string | null }) {
  return (
    <div className="grid min-w-0 gap-5">
      {docs.length === 0 ? (
        <p className="text-sm text-on-ink-muted">No documents matched for this person.</p>
      ) : (
        <ul className="grid gap-2">
          {docs.map((d) => {
            const cited = d.id === highlightDocId;
            return (
              <li
                key={d.id} data-highlighted={cited ? "true" : "false"}
                className={`flex min-w-0 items-start justify-between gap-3 rounded-control border p-3 transition ${cited ? "border-blue-bright bg-ink-3 ring-2 ring-blue-bright" : "border-ink-line bg-ink-2"}`}
              >
                <span className="min-w-0">
                  <span className="block break-words text-sm font-medium">{d.title}</span>
                  <span className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
                    <span className={chip}>{CLASSIFICATION_LABEL[d.classification] ?? d.classification}</span>
                    {cited && <span className="shrink-0 rounded-full bg-blue-bright px-2 py-0.5 text-xs font-semibold text-ink">Cited</span>}
                    <span className="num min-w-0 truncate text-xs text-on-ink-muted">{d.id}</span>
                  </span>
                </span>
                <span className="num shrink-0 text-sm font-bold">{formatScore(d.score)}</span>
              </li>
            );
          })}
        </ul>
      )}

      <div>
        <h4 className="text-sm font-semibold">Hidden by DLS ({hidden.length})</h4>
        {hidden.length === 0 ? (
          <p className="mt-2 text-sm text-on-ink-muted">Nothing was hidden for this person.</p>
        ) : (
          <>
            <p className="mt-1 text-xs text-on-ink-muted">{`Hidden from ${personaName} by document level security. Only titles are visible here.`}</p>
            <ul className="mt-2 grid gap-2">
              {hidden.map((g) => (
                <li key={g.id} className="flex min-w-0 items-center gap-3 rounded-control border border-dashed border-ink-line p-3 text-on-ink-muted">
                  <Lock size={18} weight="regular" aria-hidden className="shrink-0" />
                  <span className="min-w-0">
                    <span className="block break-words text-sm">{g.title}</span>
                    <span className={`${chip} mt-1 inline-block`}>{CLASSIFICATION_LABEL[g.classification] ?? g.classification}</span>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
