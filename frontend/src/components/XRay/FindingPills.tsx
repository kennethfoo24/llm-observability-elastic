import { ExtLink } from "./ExtLink";

export type Pill = { key: string; label: string; href?: string; tag?: string };

const PILL = "inline-flex min-w-0 items-center gap-2 break-words rounded-full px-3 py-1 text-sm font-medium transition";
const TONE = { flag: "bg-flag-soft text-flag-ink hover:brightness-95", warn: "bg-cost/30 text-on-ink hover:bg-cost/45" } as const;

/** Only findings that triggered: each pill links to where Elastic recorded it. */
export function FindingPills({ pills, tone, label }: { pills: Pill[]; tone: keyof typeof TONE; label: string }) {
  return (
    <ul aria-label={label} className="flex flex-wrap gap-2">
      {pills.map((p) => (
        <li key={p.key} className="min-w-0">
          {p.href ? (
            <ExtLink href={p.href} icon={false} className={`${PILL} ${TONE[tone]} underline-offset-2 hover:underline`}>
              {p.tag && <span className="num text-xs font-bold">{p.tag}</span>}{p.label}
            </ExtLink>
          ) : (
            <span className={`${PILL} ${TONE[tone]}`}>{p.tag && <span className="num text-xs font-bold">{p.tag}</span>}{p.label}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
