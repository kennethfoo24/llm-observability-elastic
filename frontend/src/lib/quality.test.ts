import { isAnswered, qualityInput } from "./quality";
import type { ChatResponse } from "./types";

test("the not-in-the-documents reply and refusals are not answered", () => {
  expect(isAnswered("I couldn't find anything about that in the documents you have access to. Try rephrasing.")).toBe(false);
  expect(isAnswered("I’m sorry, I don't have information about that.")).toBe(false);
  expect(isAnswered("The provided documents do not mention the CEO.")).toBe(false);
  expect(isAnswered("I was unable to find a clause number.")).toBe(false);
  expect(isAnswered("   ")).toBe(false);
});

test("a normal cited answer is answered", () => {
  expect(isAnswered("You get 25 days of paid time off [pto-policy].")).toBe(true);
});

const r = {
  answer: "You get 25 days [pto-policy] and see [ghost-doc, remote-work].", blocked: false, persona: "employee",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.2 }, { id: "remote-work", title: "Remote Work", classification: "public", score: 5.5 }],
  hidden: [{ id: "x", title: "X", classification: "restricted" }],
} as unknown as ChatResponse;

test("qualityInput mirrors what the app logs", () => {
  expect(qualityInput(r, "How many PTO days?")).toEqual({
    prompt: "How many PTO days?", response: r.answer, context: "[pto-policy] Paid Time Off Policy\n[remote-work] Remote Work",
    citedIds: ["pto-policy", "remote-work"], retrievedIds: ["pto-policy", "remote-work"], topScore: 5.5, hiddenCount: 1, answered: true, persona: "employee",
  });
});

test("qualityInput uses a zero top score when nothing was retrieved", () => {
  expect(qualityInput({ ...r, docs: [] }, "q").topScore).toBe(0);
});
