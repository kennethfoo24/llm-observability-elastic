import { CoinIcon } from "./icons";
import { formatCost } from "../lib/format";

export function CostBadge({ spendUsd }: { spendUsd: number }) {
  return (
    <div className="flex items-center gap-2 whitespace-nowrap rounded-full bg-white px-3.5 py-2 text-[13px] text-muted" title="Total model cost of this conversation">
      <CoinIcon size={15} aria-hidden />
      <span>Session cost</span>
      <span className="num font-bold text-ink">{formatCost(spendUsd)}</span>
    </div>
  );
}
