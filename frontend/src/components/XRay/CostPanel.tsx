import { formatCost, formatTokens } from "../../lib/format";
import { costDashboardUrl } from "../../lib/kibanaLinks";
import { ExtLink } from "./ExtLink";
import type { ChatResponse } from "../../lib/types";

export function CostPanel({ r, kibanaUrl }: { r: ChatResponse; kibanaUrl?: string }) {
  const stat = (label: string, value: number) => (
    <div className="min-w-0">
      <dt className="text-xs text-on-ink-muted">{label}</dt>
      <dd className="num mt-0.5 break-all font-bold">{formatTokens(Number.isFinite(value) ? value : 0)}</dd>
    </div>
  );
  return (
    <div className="min-w-0">
      <div className="border-l-2 border-cost pl-3">
        <p className="text-xs text-on-ink-muted">Cost of this answer</p>
        <p className="num break-all text-3xl font-bold tracking-tight">{formatCost(r.cost_usd)}</p>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
        {stat("Input tokens", r.usage.input_tokens)}
        {stat("Output tokens", r.usage.output_tokens)}
        {stat("Thinking tokens", r.usage.thinking_tokens)}
      </dl>
      <p className="num mt-4 break-all text-xs text-on-ink-muted">{r.model}</p>
      {kibanaUrl && <div className="mt-4"><ExtLink href={costDashboardUrl(kibanaUrl)}>Open cost dashboard</ExtLink></div>}
    </div>
  );
}
