import { render, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { XRayDrawer } from "./XRayDrawer";
import type { AssistantMsg } from "../../state/chatState";
import type { ChatResponse, Persona } from "../../lib/types";

const maya: Persona = { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 };
const response = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "a", blocked: false, block_reason: [], trace_id: "4bf92f3577b34da6a3ce929d0e0e4736", persona: "employee", model: "gemini-3.1-flash-lite", engine: "sdk",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.2 }],
  hidden: [{ id: "project-aurora", title: "Project Aurora: Platform and Data Reorganisation", classification: "restricted" }],
  usage: { input_tokens: 3120, output_tokens: 410, thinking_tokens: 75 }, cost_usd: 0.00135,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 41, injection_score: 0.02 },
  stages: [{ name: "guardrail.check", ms: 41 }, { name: "retrieval.hybrid", ms: 120 }, { name: "prompt.build", ms: 2 }, { name: "llm.generate", ms: 780 }], ...over,
});
const msg = (r: ChatResponse | undefined, over: Partial<AssistantMsg> = {}): AssistantMsg => ({
  id: "a1", kind: "assistant", replyTo: "u1", persona: "employee", model: "flash-lite", engine: "sdk", status: r ? "done" : "pending", response: r, ...over,
});
const props = { persona: maya, question: "How many PTO days?", kibanaUrl: "https://kb.example", highlightDocId: null };

test("empty state explains what will appear", () => {
  render(<XRayDrawer {...props} msg={null} />);
  expect(screen.getByRole("heading", { name: "X-ray" })).toBeInTheDocument();
  expect(screen.getByText(/send a question to see/i)).toBeInTheDocument();
});

test("pending shows a busy skeleton", () => {
  render(<XRayDrawer {...props} msg={msg(undefined)} />);
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
});

test("a done answer shows all four sections and the Kibana deep link", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  for (const h of ["Guardrail", "Trace", "Retrieval", "Model and cost"]) expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /open trace in kibana/i });
  expect(link).toHaveAttribute("href", "https://kb.example/app/apm/link-to/trace/4bf92f3577b34da6a3ce929d0e0e4736");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
});

test("waterfall lists every stage with its duration", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  const trace = screen.getByRole("region", { name: "Trace" });
  for (const label of ["Guardrail check", "Hybrid search", "Prompt build", "LLM call"]) expect(within(trace).getByText(label)).toBeInTheDocument();
  expect(within(trace).getByText("780 ms")).toBeInTheDocument();
});

test("retrieval shows readable documents and ghost cards for what DLS hid, naming the person", () => {
  render(<XRayDrawer {...props} msg={msg(response())} highlightDocId="pto-policy" />);
  const retrieval = screen.getByRole("region", { name: "Retrieval" });
  expect(within(retrieval).getByText("Paid Time Off Policy")).toBeInTheDocument();
  expect(within(retrieval).getByText("3.2")).toBeInTheDocument();
  expect(within(retrieval).getByRole("heading", { name: /hidden by dls \(1\)/i })).toBeInTheDocument();
  expect(within(retrieval).getByText(/project aurora/i)).toBeInTheDocument();
  expect(within(retrieval).getByText(/hidden from maya lim by document level security/i)).toBeInTheDocument();
  expect(within(retrieval).getByText("Paid Time Off Policy").closest("li")).toHaveAttribute("data-highlighted", "true");
});

test("nothing hidden says so instead of rendering an empty list", () => {
  render(<XRayDrawer {...props} msg={msg(response({ hidden: [] }))} />);
  expect(screen.getByText(/nothing was hidden for this person/i)).toBeInTheDocument();
});

test("model and cost show tokens, thinking tokens and cost in monospace numbers", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  const cost = screen.getByRole("region", { name: "Model and cost" });
  expect(within(cost).getByText("$0.00135")).toBeInTheDocument();
  expect(within(cost).getByText("3,120")).toBeInTheDocument();
  expect(within(cost).getByText("410")).toBeInTheDocument();
  expect(within(cost).getByText("75")).toBeInTheDocument();
  expect(within(cost).getByText("gemini-3.1-flash-lite")).toBeInTheDocument();
});

test("a flagged blocked prompt shows the verdict in words and its reasons, and no retrieval section content", () => {
  const blocked = response({ blocked: true, answer: "", docs: [], hidden: [], cost_usd: 0, usage: { input_tokens: 0, output_tokens: 0, thinking_tokens: 0 },
    block_reason: ["prompt_injection"], guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection"], status: "ok", latency_ms: 30, injection_score: 0.99 }, stages: [{ name: "guardrail.check", ms: 30 }] });
  render(<XRayDrawer {...props} msg={msg(blocked)} />);
  const g = screen.getByRole("region", { name: "Guardrail" });
  expect(within(g).getByText("Flagged")).toBeInTheDocument();
  expect(within(g).getByText("Prompt injection attempt")).toBeInTheDocument();
  expect(within(g).getByText("0.99")).toBeInTheDocument();
  expect(screen.getByText(/stopped before any search or model call/i)).toBeInTheDocument();
});

test("degraded guardrail shows a Degraded badge", () => {
  render(<XRayDrawer {...props} msg={msg(response({ guardrail: { verdict: "CLEAN", reasons: [], status: "degraded", latency_ms: 1500, injection_score: 0 } }))} />);
  expect(screen.getByText("Degraded")).toBeInTheDocument();
});

test("missing kibana url or trace id shows a muted note instead of a broken link", () => {
  render(<XRayDrawer {...props} kibanaUrl={undefined} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /open trace/i })).toBeNull();
  expect(screen.getByText(/trace link unavailable/i)).toBeInTheDocument();
});

test("an errored message says there is no trace", () => {
  render(<XRayDrawer {...props} msg={msg(undefined, { status: "error", error: { status: 502, code: "upstream_error" } })} />);
  expect(screen.getByText(/no trace for a failed request/i)).toBeInTheDocument();
});

test("has no obvious accessibility violations", async () => {
  const { container } = render(<XRayDrawer {...props} msg={msg(response())} />);
  expect(await axe(container)).toHaveNoViolations();
});

test("empty stages render a muted note instead of an empty list", () => {
  render(<XRayDrawer {...props} msg={msg(response({ stages: [] }))} />);
  const trace = screen.getByRole("region", { name: "Trace" });
  expect(within(trace).getByText("No timing data")).toBeInTheDocument();
  expect(within(trace).queryByRole("list")).toBeNull();
});

test("docs empty with hidden non-empty still shows the ghost cards", () => {
  render(<XRayDrawer {...props} msg={msg(response({ docs: [] }))} />);
  const retrieval = screen.getByRole("region", { name: "Retrieval" });
  expect(within(retrieval).getByText(/no documents matched/i)).toBeInTheDocument();
  expect(within(retrieval).getByText(/project aurora/i)).toBeInTheDocument();
});

test("the highlighted document carries a Cited text badge, not only a ring", () => {
  render(<XRayDrawer {...props} msg={msg(response())} highlightDocId="pto-policy" />);
  const retrieval = screen.getByRole("region", { name: "Retrieval" });
  expect(within(retrieval).getByText("Cited")).toBeInTheDocument();
});

test("without a highlight no Cited badge is shown", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  expect(screen.queryByText("Cited")).toBeNull();
});

test("scores are rounded to at most two decimals", () => {
  render(<XRayDrawer {...props} msg={msg(response({ docs: [
    { id: "a", title: "A", classification: "public", score: 123.456789 },
    { id: "b", title: "B", classification: "public", score: 0 },
  ] }))} />);
  expect(screen.getByText("123.46")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
});

test("a missing trace id shows the unavailable note and never prints the id", () => {
  render(<XRayDrawer {...props} msg={msg(response({ trace_id: "" }))} />);
  expect(screen.queryByRole("link", { name: /open trace/i })).toBeNull();
  expect(screen.getByText(/trace link unavailable/i)).toBeInTheDocument();
});

test("the trace id appears only in the link href", () => {
  const { container } = render(<XRayDrawer {...props} msg={msg(response())} />);
  expect(container.textContent).not.toContain("4bf92f3577b34da6a3ce929d0e0e4736");
});

test("hostile content: long titles, long ids, 50 hidden docs and huge usage stay contained", async () => {
  const long = "W".repeat(200);
  const id80 = "x".repeat(80);
  const hidden = Array.from({ length: 50 }, (_, i) => ({ id: `h${i}`, title: `${long}${i}`, classification: "restricted" }));
  const { container } = render(<XRayDrawer {...props} highlightDocId={id80} msg={msg(response({
    docs: [{ id: id80, title: long, classification: "public", score: 1 }],
    hidden,
    usage: { input_tokens: 9_999_999_999_999, output_tokens: 8_888_888_888_888, thinking_tokens: 7_777_777_777_777 },
    cost_usd: 123456789.5,
    model: "m".repeat(120),
  }))} />);
  const retrieval = screen.getByRole("region", { name: "Retrieval" });
  expect(within(retrieval).getByRole("heading", { name: /hidden by dls \(50\)/i })).toBeInTheDocument();
  expect(within(retrieval).getAllByText(/^W{200}/)).toHaveLength(51);
  // every long-text holder opts into wrapping or truncation so it cannot widen the panel
  for (const el of Array.from(container.querySelectorAll("li")).filter((l) => (l.textContent ?? "").includes(long))) {
    expect(el.className).toMatch(/min-w-0|overflow-hidden/);
    expect(el.innerHTML).toMatch(/break-words|break-all|truncate/);
  }
  expect(await axe(container)).toHaveNoViolations();
});
