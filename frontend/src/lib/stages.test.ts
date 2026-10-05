import { layoutStages } from "./stages";

test("stages are laid out sequentially against the total", () => {
  const rows = layoutStages([
    { name: "guardrail.check", ms: 100 },
    { name: "retrieval.hybrid", ms: 300 },
    { name: "llm.generate", ms: 600 },
  ]);
  expect(rows.map((r) => r.label)).toEqual(["Guardrail check", "Hybrid search", "LLM call"]);
  expect(rows[0].offsetPct).toBe(0);
  expect(rows[1].offsetPct).toBeCloseTo(10);
  expect(rows[2].offsetPct).toBeCloseTo(40);
  expect(rows.reduce((a, r) => a + r.widthPct, 0)).toBeCloseTo(100, 0);
});

test("tiny stages keep a visible minimum width and never overflow", () => {
  const rows = layoutStages([{ name: "guardrail.check", ms: 1 }, { name: "llm.generate", ms: 1999 }]);
  expect(rows[0].widthPct).toBeGreaterThanOrEqual(1.5);
  const last = rows[rows.length - 1];
  expect(last.offsetPct + last.widthPct).toBeLessThanOrEqual(100.0001);
});

test("empty or zero-duration input does not divide by zero", () => {
  expect(layoutStages([])).toEqual([]);
  const rows = layoutStages([{ name: "prompt.build", ms: 0 }]);
  expect(Number.isFinite(rows[0].widthPct)).toBe(true);
});

test("unknown stage names fall back to the raw name", () => {
  expect(layoutStages([{ name: "custom.step", ms: 5 }])[0].label).toBe("custom.step");
});

test("a tiny last stage is shifted left so offset + width never exceeds 100", () => {
  const rows = layoutStages([{ name: "llm.generate", ms: 1999 }, { name: "guardrail.check", ms: 1 }]);
  for (const r of rows) expect(r.offsetPct + r.widthPct).toBeLessThanOrEqual(100.0001);
  expect(rows[1].widthPct).toBeGreaterThanOrEqual(1.5);
});
