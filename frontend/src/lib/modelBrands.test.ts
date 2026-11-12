import { describe, expect, it } from "vitest";
import { brandFor } from "./modelBrands";

const m = (key: string, provider: "eis" | "gemma", model_id: string) => ({ key, provider, model_id });

describe("brandFor", () => {
  it("maps the four catalog models", () => {
    expect(brandFor(m("eis-gpt-mini", "eis", "gpt-5.4-mini")).key).toBe("openai");
    expect(brandFor(m("eis-claude-haiku", "eis", "claude-4.5-haiku")).key).toBe("claude");
    expect(brandFor(m("eis-gemini-flash", "eis", "gemini-3.5-flash")).key).toBe("gemini");
    expect(brandFor(m("gemma", "gemma", "google/gemma-4-31b")).key).toBe("gemma");
  });
  it("falls back to generic for an unknown model", () => {
    expect(brandFor(m("mystery", "eis", "mystery-1")).key).toBe("generic");
  });
});
