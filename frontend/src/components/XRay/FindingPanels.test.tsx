import { render, screen, within } from "@testing-library/react";
import { SecurityPanel } from "./SecurityPanel";
import { QualityPanel } from "./QualityPanel";
import type { ChatResponse, Findings } from "../../lib/types";

const TID = "4bf92f3577b34da6a3ce929d0e0e4736";
const r = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "You get 25 PTO days.", blocked: false, block_reason: [], trace_id: TID, persona: "employee", model: "m", engine: "langchain", docs: [], hidden: [],
  usage: { input_tokens: 1, output_tokens: 1, thinking_tokens: 0 }, cost_usd: 0,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 1, injection_score: 0.01 }, stages: [], ...over,
});
const ready = (security: string[] = [], quality: string[] = []): Findings => ({ status: "ready", security, quality });
const KB = "https://kb.example";

test("security shows only what triggered, each pill linked, and says so when nothing did", () => {
  const { rerender } = render(<SecurityPanel r={r()} findings={ready()} kibanaUrl={KB} />);
  expect(screen.getByText("No security findings.")).toBeInTheDocument();
  expect(screen.queryByRole("list")).toBeNull();
  rerender(<SecurityPanel r={r({ guardrail: { verdict: "FLAGGED", reasons: ["pii_email"], status: "ok", latency_ms: 1, injection_score: 0.1 } })} findings={ready(["unsafe_markup"])} kibanaUrl={KB} securityKibanaUrl="https://sec.example" />);
  const list = within(screen.getByRole("list", { name: "Security findings" }));
  expect(list.getAllByRole("listitem")).toHaveLength(2);
  expect(list.getByRole("link", { name: /email address/i })).toHaveAttribute("href", expect.stringContaining("https://sec.example"));
  const out = list.getByRole("link", { name: /unsafe markup in the answer/i });
  expect(out).toHaveTextContent("LLM05");
  expect(out.getAttribute("href")).toContain("https://kb.example/app/discover");
  expect(screen.queryByText("No security findings.")).toBeNull();
});

test("security says scoring is in progress while the response log is not written yet", () => {
  render(<SecurityPanel r={r()} findings={{ status: "pending", security: [], quality: [] }} kibanaUrl={KB} />);
  expect(screen.getByRole("status")).toHaveTextContent(/still scoring/i);
  expect(screen.queryByText("No security findings.")).toBeNull();
});

test("quality shows only the triggered pills, linked to the response log", () => {
  render(<QualityPanel r={r()} findings={ready([], ["off_topic", "negative_sentiment"])} kibanaUrl={KB} />);
  const list = within(screen.getByRole("list", { name: "Quality findings" }));
  expect(list.getAllByRole("listitem")).toHaveLength(2);
  expect(list.getByRole("link", { name: /off topic/i }).getAttribute("href")).toContain("https://kb.example/app/discover");
  expect(screen.queryByText(/language mismatch/i)).toBeNull();
});

test("quality shows a failure to answer immediately, before Elastic has scored", () => {
  render(<QualityPanel r={r({ answer: "I couldn't find anything about that in the documents you have access to." })} findings={{ status: "pending", security: [], quality: [] }} kibanaUrl={KB} />);
  expect(screen.getByRole("link", { name: /did not answer/i })).toBeInTheDocument();
});

test("a clean, scored answer reports no quality findings", () => {
  render(<QualityPanel r={r()} findings={ready()} kibanaUrl={KB} />);
  expect(screen.getByText("No quality findings.")).toBeInTheDocument();
});
