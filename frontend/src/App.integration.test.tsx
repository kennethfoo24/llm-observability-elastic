import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { auth } from "./lib/api";
import * as apiMod from "./lib/api";
import type { ChatResponse } from "./lib/types";

const personas = [
  { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 },
  { id: "exec", name: "Rachel Tan", title: "Chief People Officer", can_read_docs: 20, total_docs: 20 },
];
const models = [
  { key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis" as const, model_id: "g1", available: true },
  { key: "gemma", label: "Gemma 4 31B (self-hosted)", provider: "gemma" as const, model_id: "gm", available: false },
];
const answer = (over: Partial<ChatResponse>): ChatResponse => ({
  answer: "Employees get 18 days [pto-policy].", blocked: false, block_reason: [], trace_id: "abc123", persona: "employee", model: "g1", engine: "sdk",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.1 }],
  hidden: [{ id: "project-aurora", title: "Project Aurora", classification: "restricted" }],
  usage: { input_tokens: 100, output_tokens: 20, thinking_tokens: 0 }, cost_usd: 0.0004,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 30, injection_score: 0.01 },
  stages: [{ name: "guardrail.check", ms: 30 }, { name: "retrieval.hybrid", ms: 100 }, { name: "prompt.build", ms: 2 }, { name: "llm.generate", ms: 500 }], ...over,
});

beforeEach(() => {
  auth.set("pw");
  vi.spyOn(apiMod.api, "personas").mockResolvedValue(personas);
  vi.spyOn(apiMod.api, "models").mockResolvedValue(models);
  vi.spyOn(apiMod.api, "config").mockResolvedValue({ kibana_url: "https://kb", company: "Nimbus Corp" });
});

test("ask a suggested question, see the answer, the cost and the x-ray", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  expect(await screen.findByText(/employees get 18 days/i)).toBeInTheDocument();
  const xray = screen.getByRole("region", { name: "X-ray" });
  expect(await within(xray).findByText("Paid Time Off Policy")).toBeInTheDocument();
  expect(within(xray).getByText(/hidden from maya lim/i)).toBeInTheDocument();
  expect(screen.getAllByText("$0.0004").length).toBeGreaterThan(0);
});

test("switching persona offers to ask the same question again and the new answer differs", async () => {
  const chat = vi.spyOn(apiMod.api, "chat")
    .mockResolvedValueOnce(answer({ answer: "I could not find that.", docs: [], persona: "employee" }))
    .mockResolvedValueOnce(answer({ answer: "The Aurora severance budget is 2.1 million dollars [project-aurora].", docs: [{ id: "project-aurora", title: "Project Aurora", classification: "restricted", score: 4 }], hidden: [], persona: "exec" }));
  render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /your question/i }), "What is the Project Aurora severance budget?{Enter}");
  expect(await screen.findByText(/could not find that/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: /rachel tan/i }));
  await userEvent.click(await screen.findByRole("button", { name: /ask again as rachel tan/i }));
  expect(await screen.findByText(/2\.1 million/i)).toBeInTheDocument();
  expect(chat).toHaveBeenLastCalledWith({ message: "What is the Project Aurora severance budget?", persona: "exec", model: "eis-gpt-mini", engine: "sdk" });
});

test("a blocked red-team prompt shows the block card and the x-ray says nothing was billed", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({ blocked: true, answer: "", block_reason: ["prompt_injection"], docs: [], hidden: [], cost_usd: 0, guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection"], status: "ok", latency_ms: 25, injection_score: 0.99 }, stages: [{ name: "guardrail.check", ms: 25 }] }));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /red team/i }));
  await userEvent.click(await screen.findByRole("button", { name: /ignore previous instructions/i }));
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  expect(await screen.findByRole("heading", { name: /blocked by the guardrail/i })).toBeInTheDocument();
  expect(screen.getByText(/stopped before any search or model call/i)).toBeInTheDocument();
});

test("the offline Gemma model is visible but cannot be selected", async () => {
  render(<App />);
  const gemma = await screen.findByRole("radio", { name: /gemma/i });
  expect(gemma).toBeDisabled();
  expect(screen.getByText("Offline")).toBeInTheDocument();
});

test("new conversation clears the thread and the session cost", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await screen.findByText(/employees get 18 days/i);
  await userEvent.click(screen.getByRole("button", { name: /new conversation/i }));
  await waitFor(() => expect(screen.queryByText(/employees get 18 days/i)).toBeNull());
  expect(screen.getByText("$0")).toBeInTheDocument();
});

test("a 401 mid-session returns to the gate, keeps the typed draft, and unlocking restores it without looping", async () => {
  // the real request() notifies the unauthorized subscribers on a 401 and throws ApiError(401)
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 })));
  render(<App />);
  const box = await screen.findByRole("textbox", { name: /your question/i });
  await userEvent.type(box, "my unsent draft");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  const pw = await screen.findByLabelText(/demo password/i);
  expect(auth.get()).toBe("");
  // no reload loop: the bootstrap endpoints were each called once so far
  expect(apiMod.api.personas).toHaveBeenCalledTimes(1);
  await userEvent.type(pw, "pw{Enter}");
  expect(await screen.findByRole("textbox", { name: /your question/i })).toHaveValue("my unsent draft");
  expect(apiMod.api.personas).toHaveBeenCalledTimes(2);
  vi.unstubAllGlobals();
});

test("an upstream error shows a recoverable inline error with a retry that works", async () => {
  vi.spyOn(apiMod.api, "chat")
    .mockRejectedValueOnce(new apiMod.ApiError(503, "gemma_offline"))
    .mockResolvedValueOnce(answer({}));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  const retry = await screen.findByRole("button", { name: /try again|retry/i });
  await userEvent.click(retry);
  expect(await screen.findByText(/employees get 18 days/i)).toBeInTheDocument();
});

function mockViewport(wide: boolean) {
  let matches = wide;
  const listeners = new Set<(e: { matches: boolean }) => void>();
  vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({
    get matches() { return matches; }, media: q, onchange: null,
    addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.delete(cb),
    addListener() {}, removeListener() {}, dispatchEvent: () => false,
  }) as unknown as MediaQueryList);
  return { set: (v: boolean) => { matches = v; act(() => listeners.forEach((cb) => cb({ matches: v }))); } };
}
const mockSmall = (small: boolean) => mockViewport(!small);

async function askPto() {
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await screen.findByText(/employees get 18 days/i);
}

test("on a small screen the message Inspect button opens the x-ray sheet, Escape closes it and focus returns", async () => {
  mockSmall(true);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  expect(screen.queryByRole("button", { name: /inspect x-ray/i })).toBeNull();
  const inspect = screen.getByRole("button", { name: /^inspect$/i });
  await userEvent.click(inspect);
  const dialog = await screen.findByRole("dialog", { name: "X-ray" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(screen.getByRole("button", { name: /close x-ray/i })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: /^inspect$/i })).toHaveFocus());
});

test("on desktop the message Inspect button only selects, it does not open the sheet", async () => {
  mockSmall(false);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: /^inspect$/i }));
  expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull();
});

test("clicking the scrim closes the x-ray sheet", async () => {
  mockSmall(true);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: /^inspect$/i }));
  await screen.findByRole("dialog", { name: "X-ray" });
  await userEvent.click(screen.getByTestId("xray-scrim"));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull());
});

test("the rail disclosure is collapsed by default, toggles aria-expanded and keeps the summary current after a persona change", async () => {
  render(<App />);
  const toggle = await screen.findByRole("button", { name: /change person or model/i });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByText(/asking as/i, { selector: "p" })).toHaveTextContent("Asking as Maya Lim, GPT-5.4 mini");
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(document.getElementById(toggle.getAttribute("aria-controls")!)).toContainElement(screen.getByRole("radio", { name: /rachel tan/i }));
  await userEvent.click(screen.getByRole("radio", { name: /rachel tan/i }));
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/asking as/i, { selector: "p" })).toHaveTextContent("Asking as Rachel Tan, GPT-5.4 mini");
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test("picking a model by click closes the open disclosure and returns focus to its toggle, picking a persona keeps it open", async () => {
  render(<App />);
  const toggle = await screen.findByRole("button", { name: /change person or model/i });
  await userEvent.click(toggle);
  await userEvent.click(screen.getByRole("radio", { name: /rachel tan/i }));
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(screen.getByRole("radio", { name: /gpt-5\.4 mini/i }));
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle).toHaveFocus();
});

test("arrowing through the models with the keyboard does not close the disclosure", async () => {
  render(<App />);
  const toggle = await screen.findByRole("button", { name: /change person or model/i });
  await userEvent.click(toggle);
  screen.getByRole("radio", { name: /gpt-5\.4 mini/i }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(toggle).toHaveAttribute("aria-expanded", "true");
});

test("the red-team pick appends to a non-empty draft on a new line and sets an empty one", async () => {
  render(<App />);
  const box = await screen.findByRole("textbox", { name: /your question/i });
  await userEvent.click(screen.getByRole("button", { name: /red team/i }));
  await userEvent.click(await screen.findByRole("button", { name: /ignore previous instructions/i }));
  const first = (box as HTMLTextAreaElement).value;
  expect(first).toMatch(/ignore previous instructions/i);
  await userEvent.clear(box);
  await userEvent.type(box, "my own text");
  await userEvent.click(screen.getByRole("button", { name: /red team/i }));
  await userEvent.click(await screen.findByRole("button", { name: /ignore previous instructions/i }));
  expect((box as HTMLTextAreaElement).value).toBe(`my own text\n${first}`);
});

test("reset clears the typed draft", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  const box = screen.getByRole("textbox", { name: /your question/i });
  await userEvent.type(box, "half typed");
  await userEvent.click(screen.getByRole("button", { name: /new conversation/i }));
  await waitFor(() => expect(box).toHaveValue(""));
});

test("below xl a citation click opens the sheet and highlights the cited document", async () => {
  mockSmall(true);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: "pto-policy" }));
  const dialog = await screen.findByRole("dialog", { name: "X-ray" });
  expect(within(dialog).getByText("Paid Time Off Policy").closest("[data-highlighted]")).toHaveAttribute("data-highlighted", "true");
});

test("on desktop a citation click does not open the sheet", async () => {
  mockSmall(false);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: "pto-policy" }));
  expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull();
});

test("growing past xl closes the open sheet and releases the scroll lock", async () => {
  const vp = mockSmall(true);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  document.body.style.overflow = "";
  await userEvent.click(screen.getByRole("button", { name: /^inspect$/i }));
  await screen.findByRole("dialog", { name: "X-ray" });
  expect(document.body.style.overflow).toBe("hidden");
  vp.set(true);
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull());
  expect(document.body.style.overflow).toBe("");
});
