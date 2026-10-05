import { render, screen, waitFor, within } from "@testing-library/react";
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
  { key: "flash-lite", label: "Gemini Flash-Lite", provider: "vertex" as const, model_id: "g1", available: true },
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
  expect(chat).toHaveBeenLastCalledWith({ message: "What is the Project Aurora severance budget?", persona: "exec", model: "flash-lite", engine: "sdk" });
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

test("below lg the Inspect button opens the x-ray sheet, Escape closes it and focus returns", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await screen.findByText(/employees get 18 days/i);
  const inspect = screen.getByRole("button", { name: /inspect x-ray/i });
  await userEvent.click(inspect);
  const dialog = await screen.findByRole("dialog", { name: "X-ray" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(screen.getByRole("button", { name: /close x-ray/i })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: /inspect x-ray/i })).toHaveFocus());
});

test("clicking the scrim closes the x-ray sheet", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await screen.findByText(/employees get 18 days/i);
  await userEvent.click(screen.getByRole("button", { name: /inspect x-ray/i }));
  await screen.findByRole("dialog", { name: "X-ray" });
  await userEvent.click(screen.getByTestId("xray-scrim"));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "X-ray" })).toBeNull());
});
