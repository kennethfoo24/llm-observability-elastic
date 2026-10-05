import { formatCost, formatMs, formatTokens } from "./format";

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
