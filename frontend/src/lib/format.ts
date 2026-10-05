export function formatCost(usd: number): string {
  if (usd === 0) return "$0";
  if (usd > 0 && usd < 0.000005) return "<$0.00001";
  if (usd < 0.01) return `$${usd.toFixed(5)}`.replace(/0+$/, "").replace(/\.$/, "");
  if (usd < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}
