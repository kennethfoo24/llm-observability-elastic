/* The demo documents were indexed by hand. Each shows the logo of a plausible origin system, to suggest
   Elastic connectors could ingest them. Keyed by the document id (the hr-kb slug). */
export type SourceKey = "confluence" | "sharepoint" | "gdrive" | "database" | "generic";

export const SOURCE_LABEL: Record<SourceKey, string> = {
  confluence: "Confluence", sharepoint: "SharePoint", gdrive: "Google Drive", database: "Database", generic: "Document",
};

const BY_SOURCE: Record<Exclude<SourceKey, "generic">, string[]> = {
  confluence: ["pto-policy", "remote-work", "code-of-conduct"],
  sharepoint: ["benefits-overview", "holiday-calendar-2026", "performance-review-guide", "promotion-criteria", "termination-checklist"],
  gdrive: ["expense-policy", "salary-bands", "headcount-plan-q4", "comp-adjustments-2026", "exec-compensation", "project-aurora", "lumen-acquisition", "layoff-contingency", "background-check-vendor"],
  database: ["attrition-report", "case-4172", "case-4188"],
};

const SOURCE_BY_DOC: Record<string, SourceKey> = Object.fromEntries(
  Object.entries(BY_SOURCE).flatMap(([source, ids]) => ids.map((id) => [id, source as SourceKey])),
);

export const sourceFor = (docId: string): SourceKey => SOURCE_BY_DOC[docId] ?? "generic";
