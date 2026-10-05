import { STAGE_LABELS } from "./copy";
import type { Stage } from "./types";

export type StageRow = { name: string; label: string; ms: number; offsetPct: number; widthPct: number };

const MIN_WIDTH = 1.5;

export function layoutStages(stages: Stage[]): StageRow[] {
  if (stages.length === 0) return [];
  const total = stages.reduce((a, s) => a + Math.max(0, s.ms), 0) || 1;
  let cursor = 0;
  return stages.map((s) => {
    const offsetPct = (cursor / total) * 100;
    const raw = (Math.max(0, s.ms) / total) * 100;
    const widthPct = Math.min(Math.max(raw, MIN_WIDTH), 100);
    const shiftedOffset = Math.min(offsetPct, 100 - widthPct);
    cursor += Math.max(0, s.ms);
    return { name: s.name, label: STAGE_LABELS[s.name] ?? s.name, ms: s.ms, offsetPct: shiftedOffset, widthPct };
  });
}
