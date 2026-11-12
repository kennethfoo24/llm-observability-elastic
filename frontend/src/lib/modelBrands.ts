export type ModelBrandKey = "openai" | "claude" | "gemini" | "gemma" | "generic";
export type ModelBrand = { key: ModelBrandKey; color: string };

const COLORS: Record<ModelBrandKey, string> = {
  openai: "#0b0f19", claude: "#d97757", gemini: "#8e75b2", gemma: "#4285f4", generic: "#535966",
};

/** Matches on the backend's model_id first, then the catalog key. Gemma has no free official mark, so it shows the Gemini mark in Google blue. */
export function brandFor(model: { key: string; provider: string; model_id: string }): ModelBrand {
  const id = `${model.model_id} ${model.key}`.toLowerCase();
  const key: ModelBrandKey =
    id.includes("gemma") ? "gemma" : id.includes("gemini") ? "gemini" : id.includes("claude") ? "claude" : id.includes("gpt") || id.includes("openai") ? "openai" : "generic";
  return { key, color: COLORS[key] };
}
