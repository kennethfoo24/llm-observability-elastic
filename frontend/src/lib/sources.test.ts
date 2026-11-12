import { describe, expect, it } from "vitest";
import { SOURCE_LABEL, sourceFor, type SourceKey } from "./sources";

const TABLE: Record<Exclude<SourceKey, "generic">, string[]> = {
  confluence: ["pto-policy", "remote-work", "code-of-conduct"],
  sharepoint: ["benefits-overview", "holiday-calendar-2026", "performance-review-guide", "promotion-criteria", "termination-checklist"],
  gdrive: ["expense-policy", "salary-bands", "headcount-plan-q4", "comp-adjustments-2026", "exec-compensation", "project-aurora", "lumen-acquisition", "layoff-contingency", "background-check-vendor"],
  database: ["attrition-report", "case-4172", "case-4188"],
};

describe("sourceFor", () => {
  for (const [source, ids] of Object.entries(TABLE)) {
    it.each(ids)(`${source}: %s`, (id) => expect(sourceFor(id)).toBe(source));
  }
  it("maps an unknown id to generic", () => expect(sourceFor("nope")).toBe("generic"));
  it("labels every source", () => {
    expect(SOURCE_LABEL).toEqual({ confluence: "Confluence", sharepoint: "SharePoint", gdrive: "Google Drive", database: "Database", generic: "Document" });
  });
});
