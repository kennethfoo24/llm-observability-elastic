import { RED_TEAM, SUGGESTIONS } from "./prompts";

const DASH = /[—–]/;

test("suggestions cover the four personas with at least three each", () => {
  expect(Object.keys(SUGGESTIONS).sort()).toEqual(["employee", "exec", "hr", "manager"]);
  for (const list of Object.values(SUGGESTIONS)) expect(list.length).toBeGreaterThanOrEqual(3);
});

test("red team prompts have unique ids, labels and bounded text", () => {
  const ids = RED_TEAM.map((r) => r.id);
  expect(new Set(ids).size).toBe(ids.length);
  for (const r of RED_TEAM) {
    expect(r.label.trim()).not.toBe("");
    expect(r.text.length).toBeLessThanOrEqual(4000);
    expect(["blocked", "flagged"]).toContain(r.expect);
  }
});

test("no em or en dashes in any visible prompt copy", () => {
  const all = [...Object.values(SUGGESTIONS).flat(), ...RED_TEAM.flatMap((r) => [r.label, r.text])];
  for (const s of all) expect(s).not.toMatch(DASH);
});
