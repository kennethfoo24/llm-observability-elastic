import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { auth } from "./lib/api";
import * as apiMod from "./lib/api";
import type { ChatResponse } from "./lib/types";

const personas = [
  { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 },
  { id: "manager", name: "Daniel Ong", title: "Engineering Manager", can_read_docs: 11, total_docs: 20 },
];
const models = [
  { key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis" as const, model_id: "g1", available: true },
  { key: "gemma", label: "Gemma 4 31B (self-hosted)", provider: "gemma" as const, model_id: "gm", available: false },
];
const answer = (over: Partial<ChatResponse>): ChatResponse => ({
  answer: "Employees get 18 days [pto-policy].", blocked: false, block_reason: [], trace_id: "abc123", persona: "employee", model: "g1", engine: "sdk",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.1 }],
  hidden: [{ id: "salary-bands", title: "Salary Bands L3 to L5", classification: "confidential" }],
  usage: { input_tokens: 100, output_tokens: 20, thinking_tokens: 0 }, cost_usd: 0.0004,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 30, injection_score: 0.01 },
  stages: [{ name: "guardrail.check", ms: 30 }, { name: "retrieval.hybrid", ms: 100 }, { name: "prompt.build", ms: 2 }, { name: "llm.generate", ms: 500 }], ...over,
});

/* Every media query answers the same: true = laptop (inline sidebar, side drawer), false = phone (off-canvas sidebar, bottom sheet). */
function viewport(wide: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(((q: string) => ({
    matches: wide, media: q, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia);
}

beforeEach(() => {
  auth.set("pw");
  viewport(true);
  vi.spyOn(apiMod.api, "personas").mockResolvedValue(personas);
  vi.spyOn(apiMod.api, "models").mockResolvedValue(models);
  vi.spyOn(apiMod.api, "config").mockResolvedValue({ kibana_url: "https://kb", company: "Foo Corp" });
});

async function askPto() {
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await screen.findByText(/employees get 18 days/i);
}

test("ask a suggested question: the answer and the session cost show, and the observability panel stays closed", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  expect(screen.getByText("$0.0004")).toBeInTheDocument();
  expect(screen.queryByRole("complementary", { name: "LLM Observability" })).toBeNull();
});

test("the View More tab opens the observability panel with the retrieval detail and Escape closes it", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: "View More" }));
  const panel = await screen.findByRole("complementary", { name: "LLM Observability" });
  expect(await within(panel).findByText("Paid Time Off Policy")).toBeInTheDocument();
  expect(within(panel).getByText(/hidden from maya lim/i)).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("complementary", { name: "LLM Observability" })).toBeNull());
});

test("clicking a status chip opens the panel", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: /guardrail passed/i }));
  expect(await screen.findByRole("complementary", { name: "LLM Observability" })).toBeInTheDocument();
});

test("a citation is a Discover link and clicking it does not open the panel", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("link", { name: /Paid Time Off Policy · Confluence/ }));
  expect(screen.queryByRole("complementary", { name: "LLM Observability" })).toBeNull();
});

test("with no Kibana URL a citation is a button that opens the panel and highlights the cited document", async () => {
  vi.spyOn(apiMod.api, "config").mockResolvedValue({ kibana_url: "", company: "Foo Corp" });
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: /Paid Time Off Policy · Confluence/ }));
  const panel = await screen.findByRole("complementary", { name: "LLM Observability" });
  expect(within(panel).getByText("Paid Time Off Policy").closest("[data-highlighted]")).toHaveAttribute("data-highlighted", "true");
});

test("a finished conversation is listed under Today after New chat and clicking it restores both messages", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: "New chat" }));
  await waitFor(() => expect(screen.queryByText(/employees get 18 days/i)).toBeNull());
  const today = screen.getByRole("region", { name: "Today" });
  const row = within(today).getByRole("button", { name: "How many PTO days do I get?" });
  await userEvent.click(row);
  expect(await screen.findByText(/employees get 18 days/i)).toBeInTheDocument();
  expect(screen.getByText("$0.0004")).toBeInTheDocument();
});

test("Ask again as Daniel Ong switches the persona, adds the divider and posts as manager", async () => {
  const chat = vi.spyOn(apiMod.api, "chat")
    .mockResolvedValueOnce(answer({ answer: "I could not find that.", docs: [], persona: "employee" }))
    .mockResolvedValueOnce(answer({ answer: "The L4 band is 98,000 to 125,000 dollars.", docs: [], persona: "manager" }));
  render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /your question/i }), "What are the salary bands for L3 to L5?{Enter}");
  expect(await screen.findByText(/could not find that/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ask again as Daniel Ong" }));
  expect(await screen.findByText(/98,000 to 125,000/i)).toBeInTheDocument();
  expect(chat).toHaveBeenLastCalledWith({ message: "What are the salary bands for L3 to L5?", persona: "manager", model: "eis-gpt-mini", engine: "langchain" });
  expect(screen.getByRole("button", { name: /Asking as Daniel Ong/ })).toBeInTheDocument();
  expect(screen.getByText(/Now asking as Daniel Ong/)).toBeInTheDocument();
});

test("a blocked prompt shows the block card and its conversation gets the pink dot", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({ blocked: true, answer: "", block_reason: ["prompt_injection"], docs: [], hidden: [], cost_usd: 0, guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection"], status: "ok", latency_ms: 30, injection_score: 0.9 } }));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Red team prompts" }));
  await userEvent.click(await screen.findByRole("button", { name: /ignore previous instructions/i }));
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("heading", { name: /blocked by the guardrail/i })).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByTitle("Blocked or flagged")).toHaveLength(1));
});

test("reloading lists the saved conversation but opens an empty chat", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  const first = render(<App />);
  await askPto();
  first.unmount();
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Ask anything" })).toBeInTheDocument();
  expect(screen.queryByText(/employees get 18 days/i)).toBeNull();
  expect(within(screen.getByRole("region", { name: "Today" })).getByRole("button", { name: "How many PTO days do I get?" })).toBeInTheDocument();
});

test("while a request is pending New chat and the history rows are disabled", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValueOnce(answer({}));
  render(<App />);
  await askPto();
  let release!: (r: ChatResponse) => void;
  vi.spyOn(apiMod.api, "chat").mockReturnValueOnce(new Promise((r) => { release = r; }));
  await userEvent.type(screen.getByRole("textbox", { name: /your question/i }), "second{Enter}");
  expect(screen.getByRole("button", { name: "New chat" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "How many PTO days do I get?" })).toBeDisabled();
  release(answer({}));
  await waitFor(() => expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled());
});

test("deleting the active conversation starts a fresh chat", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: "Delete How many PTO days do I get?" }));
  await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  expect(await screen.findByRole("heading", { name: "Ask anything" })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Today" })).toBeNull();
});

test("the app keeps working when browser storage is blocked", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  expect(screen.getByText("$0.0004")).toBeInTheDocument();
});

test("the offline Gemma model is visible in the picker but cannot be selected", async () => {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /^model:/i }));
  const gemma = await screen.findByRole("radio", { name: /gemma/i });
  expect(gemma).toBeDisabled();
  expect(screen.getByText(/Offline · Self-hosted/)).toBeInTheDocument();
});

test("the edit button on a question puts its text back in the prompt bar", async () => {
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  await askPto();
  await userEvent.click(screen.getByRole("button", { name: "Edit and resend" }));
  expect(screen.getByRole("textbox", { name: /your question/i })).toHaveValue("How many PTO days do I get?");
});

test("a 401 mid-session returns to the gate, keeps the typed draft, and unlocking restores it without looping", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 })));
  render(<App />);
  const box = await screen.findByRole("textbox", { name: /your question/i });
  await userEvent.type(box, "my unsent draft");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const pw = await screen.findByLabelText(/demo password/i);
  expect(auth.get()).toBe("");
  expect(apiMod.api.personas).toHaveBeenCalledTimes(1);
  await userEvent.type(pw, "pw{Enter}");
  expect(await screen.findByRole("textbox", { name: /your question/i })).toHaveValue("my unsent draft");
  expect(apiMod.api.personas).toHaveBeenCalledTimes(2);
  vi.unstubAllGlobals();
});

test("an upstream error shows a recoverable inline error with a retry that works", async () => {
  vi.spyOn(apiMod.api, "chat").mockRejectedValueOnce(new apiMod.ApiError(503, "gemma_offline")).mockResolvedValueOnce(answer({}));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await userEvent.click(await screen.findByRole("button", { name: /try again|retry/i }));
  expect(await screen.findByText(/employees get 18 days/i)).toBeInTheDocument();
});

test("the red-team pick appends to a non-empty draft on a new line and sets an empty one", async () => {
  render(<App />);
  const box = await screen.findByRole("textbox", { name: /your question/i });
  await userEvent.click(screen.getByRole("button", { name: "Red team prompts" }));
  await userEvent.click(await screen.findByRole("button", { name: /email address/i }));
  const first = (box as HTMLTextAreaElement).value;
  expect(first).toMatch(/alex\.tan@/);
  await userEvent.click(screen.getByRole("button", { name: "Red team prompts" }));
  await userEvent.click(await screen.findByRole("button", { name: /salary figure/i }));
  expect((box as HTMLTextAreaElement).value.startsWith(`${first}\n`)).toBe(true);
});

test("on a phone the sidebar is off-canvas: the menu opens it, choosing New chat closes it, and View More is a bottom sheet", async () => {
  viewport(false);
  vi.spyOn(apiMod.api, "chat").mockResolvedValue(answer({}));
  render(<App />);
  expect(screen.queryByRole("heading", { name: "FOO CORP HR" })).toBeNull();
  await userEvent.click(await screen.findByRole("button", { name: "Open conversations" }));
  const dialog = await screen.findByRole("dialog", { name: "Conversation history" });
  expect(within(dialog).getByRole("heading", { name: "FOO CORP HR" })).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole("button", { name: "New chat" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Conversation history" })).toBeNull());
  await userEvent.click(await screen.findByRole("button", { name: /how many pto days/i }));
  await screen.findByText(/employees get 18 days/i);
  await userEvent.click(screen.getByRole("button", { name: "View More" }));
  expect(await screen.findByRole("dialog", { name: "LLM Observability" })).toHaveAttribute("aria-modal", "true");
});
