export function formatCost(usd: number): string {
  if (!Number.isFinite(usd) || usd <= 0) return "$0";
  if (usd < 0.000005) return "<$0.00001";
  if (usd < 0.01) return `$${usd.toFixed(5)}`.replace(/0+$/, "").replace(/\.$/, "");
  if (Number(usd.toFixed(4)) < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

export function formatMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0 ms";
  const rounded = Math.round(ms);
  if (rounded < 1000) return `${rounded} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatScore(n: number): string {
  if (!Number.isFinite(n)) return "0";
  return String(Number(n.toFixed(2)));
}
