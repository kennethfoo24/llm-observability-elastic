import type { ChatResponse } from "./types";
import type { QualityInput } from "./kibanaLinks";

// Mirrors _REFUSAL_PATTERNS and NO_CONTEXT_ANSWER in backend/app/quality.py (is_answered).
const NO_CONTEXT_PREFIX = "i couldn't find anything about that in the documents you have access to.";
const REFUSAL = [
  /\bi('| a)?m sorry\b.{0,80}\b(don'?t|do not|doesn'?t|does not|cannot|can'?t|unable|not)\b/,
  /\b(provided |available )?(documents?|context|sources?)\b.{0,60}\b(don'?t|do not|doesn'?t|does not|not)\s+(include|contain|mention|cover|provide|have|specify)/,
  /\bnot (found )?in the (provided |available )?(documents?|context)\b/,
  /\bi (don'?t|do not) have (any |enough |that |specific )?(information|details|data|access)/,
  /\bi (couldn'?t|could not|cannot|can'?t|am unable to|was unable to|wasn'?t able to) (find|locate|answer|determine)/,
  /\bno (information|mention|details?|record) (is |was )?(available|found|provided|about)\b/,
  /\bcouldn'?t find anything\b/,
  /\b(unable|not able) to (find|answer|provide)\b/,
];

export function isAnswered(answer: string): boolean {
  const text = (answer ?? "").trim();
  if (!text) return false;
  const low = text.toLowerCase().replace(/’/g, "'");
  if (low.startsWith(NO_CONTEXT_PREFIX)) return false;
  return !REFUSAL.some((p) => p.test(low));
}

/** Best effort copy of what the app logged for this answer. The client has titles, not snippets, so context is short. */
export function qualityInput(r: ChatResponse, prompt: string): QualityInput {
  const retrievedIds = r.docs.map((d) => d.id);
  const cited = new Set<string>();
  for (const m of r.answer.matchAll(/\[([^[\]\n]{1,200})\]/g)) for (const tok of m[1].split(/[,;]/)) cited.add(tok.trim());
  return {
    prompt, response: r.answer,
    context: r.docs.map((d) => `[${d.id}] ${d.title}`).join("\n"),
    citedIds: retrievedIds.filter((id) => cited.has(id)),
    retrievedIds,
    topScore: r.docs.reduce((m, d) => (Number.isFinite(d.score) ? Math.max(m, d.score) : m), 0),
    hiddenCount: r.hidden.length,
    answered: isAnswered(r.answer),
    persona: r.persona,
  };
}
