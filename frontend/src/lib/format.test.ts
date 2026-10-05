import { formatCost, formatMs, formatScore, formatTokens } from "./format";

test("formatCost keeps small LLM costs readable", () => {
  expect(formatCost(0)).toBe("$0");
  expect(formatCost(0.00135)).toBe("$0.00135");
  expect(formatCost(0.0000109)).toBe("$0.00001");
  expect(formatCost(0.0345)).toBe("$0.0345");
  expect(formatCost(1.5)).toBe("$1.50");
  expect(formatCost(0.000004)).toBe("<$0.00001");
  expect(formatCost(0.0099999)).toBe("$0.01");
});

test("formatMs switches to seconds at one second", () => {
  expect(formatMs(0)).toBe("0 ms");
  expect(formatMs(412)).toBe("412 ms");
  expect(formatMs(1850)).toBe("1.85 s");
});

test("formatTokens groups thousands", () => {
  expect(formatTokens(950)).toBe("950");
  expect(formatTokens(3120)).toBe("3,120");
});

test("formatCost branches on the rounded value", () => {
  expect(formatCost(0.99996)).toBe("$1.00");
  expect(formatCost(0.00999996)).toBe("$0.01");
});

test("formatCost never renders NaN or negative amounts", () => {
  expect(formatCost(Number.NaN)).toBe("$0");
  expect(formatCost(Number.POSITIVE_INFINITY)).toBe("$0");
  expect(formatCost(-0.5)).toBe("$0");
});

test("formatMs rounds before choosing the unit and guards bad input", () => {
  expect(formatMs(999.6)).toBe("1.00 s");
  expect(formatMs(999.4)).toBe("999 ms");
  expect(formatMs(Number.NaN)).toBe("0 ms");
  expect(formatMs(-5)).toBe("0 ms");
  expect(formatMs(Number.POSITIVE_INFINITY)).toBe("0 ms");
});

test("formatScore shows at most two decimals", () => {
  expect(formatScore(3.2)).toBe("3.2");
  expect(formatScore(0)).toBe("0");
  expect(formatScore(123.456789)).toBe("123.46");
  expect(formatScore(Number.NaN)).toBe("0");
});
