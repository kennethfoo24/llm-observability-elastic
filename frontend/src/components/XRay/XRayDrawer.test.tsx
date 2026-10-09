import { render, screen, within } from "@testing-library/react";
import { decompressFromEncodedURIComponent } from "lz-string";
import { axe } from "vitest-axe";
import { XRayDrawer } from "./XRayDrawer";
import type { AssistantMsg } from "../../state/chatState";
import type { ChatResponse, Persona } from "../../lib/types";

const maya: Persona = { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 };
const response = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: "a", blocked: false, block_reason: [], trace_id: "4bf92f3577b34da6a3ce929d0e0e4736", persona: "employee", model: "gpt-5.4-mini", engine: "sdk",
  docs: [{ id: "pto-policy", title: "Paid Time Off Policy", classification: "public", score: 3.2 }],
  hidden: [{ id: "project-aurora", title: "Project Aurora: Platform and Data Reorganisation", classification: "restricted" }],
  usage: { input_tokens: 3120, output_tokens: 410, thinking_tokens: 75 }, cost_usd: 0.00135,
  guardrail: { verdict: "CLEAN", reasons: [], status: "ok", latency_ms: 41, injection_score: 0.02 },
  stages: [{ name: "guardrail.check", ms: 41 }, { name: "retrieval.hybrid", ms: 120 }, { name: "prompt.build", ms: 2 }, { name: "llm.generate", ms: 780 }], ...over,
});
const msg = (r: ChatResponse | undefined, over: Partial<AssistantMsg> = {}): AssistantMsg => ({
  id: "a1", kind: "assistant", replyTo: "u1", persona: "employee", model: "eis-gpt-mini", engine: "sdk", status: r ? "done" : "pending", response: r, ...over,
});
const props = { persona: maya, question: "How many PTO days?", kibanaUrl: "https://kb.example", highlightDocId: null };

test("empty state explains what will appear", () => {
  render(<XRayDrawer {...props} msg={null} />);
  expect(screen.getByRole("heading", { name: "LLM Observability" })).toBeInTheDocument();
  expect(screen.getByText(/send a question to see/i)).toBeInTheDocument();
});

test("pending shows a busy skeleton", () => {
  render(<XRayDrawer {...props} msg={msg(undefined)} />);
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
});

test("a done answer shows every section and the Kibana deep link", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  for (const h of ["Guardrail", "Security", "Quality", "Trace", "Retrieval", "Cost"]) expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
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
  const cost = screen.getByRole("region", { name: "Cost" });
  expect(within(cost).getByText("$0.00135")).toBeInTheDocument();
  expect(within(cost).getByText("3,120")).toBeInTheDocument();
  expect(within(cost).getByText("410")).toBeInTheDocument();
  expect(within(cost).getByText("75")).toBeInTheDocument();
  expect(within(cost).getByText("gpt-5.4-mini")).toBeInTheDocument();
});

test("a blocked prompt says Blocked in the guardrail panel, with its reasons under Security, and no retrieval section content", () => {
  const blocked = response({ blocked: true, answer: "", docs: [], hidden: [], cost_usd: 0, usage: { input_tokens: 0, output_tokens: 0, thinking_tokens: 0 },
    block_reason: ["prompt_injection"], guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection"], status: "ok", latency_ms: 30, injection_score: 0.99 }, stages: [{ name: "guardrail.check", ms: 30 }] });
  render(<XRayDrawer {...props} msg={msg(blocked)} />);
  const g = screen.getByRole("region", { name: "Guardrail" });
  expect(within(g).getByText("Blocked")).toBeInTheDocument();
  expect(within(g).queryByText("Flagged")).toBeNull();
  expect(within(g).queryByText("Prompt injection attempt")).toBeNull();
  expect(within(screen.getByRole("region", { name: "Security" })).getByText("Prompt injection attempt")).toBeInTheDocument();
  expect(within(g).getByText("0.99")).toBeInTheDocument();
  expect(screen.getByText(/stopped before any search or model call/i)).toBeInTheDocument();
});

test("degraded guardrail shows a Degraded badge", () => {
  render(<XRayDrawer {...props} msg={msg(response({ guardrail: { verdict: "CLEAN", reasons: [], status: "degraded", latency_ms: 1500, injection_score: null } }))} />);
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

test("two drawers mounted together never share section ids", () => {
  const { container } = render(<><XRayDrawer {...props} msg={msg(response())} /><XRayDrawer {...props} msg={msg(response())} /></>);
  const ids = Array.from(container.querySelectorAll("[id]")).map((n) => n.id);
  expect(new Set(ids).size).toBe(ids.length);
  for (const sec of Array.from(container.querySelectorAll("section[aria-labelledby]"))) {
    expect(container.querySelectorAll(`#${CSS.escape(sec.getAttribute("aria-labelledby")!)}`)).toHaveLength(1);
  }
});

test("the Kibana link encodes the trace id and says it opens in a new tab", () => {
  render(<XRayDrawer {...props} msg={msg(response({ trace_id: "a/b c" }))} />);
  const link = screen.getByRole("link", { name: /open trace in kibana/i });
  expect(link).toHaveAttribute("href", "https://kb.example/app/apm/link-to/trace/a%2Fb%20c");
  expect(link).toHaveTextContent("(opens in a new tab)");
});

const patternsOnly = (over: Partial<ChatResponse["guardrail"]> = {}) =>
  response({ guardrail: { verdict: "CLEAN", reasons: [], status: "degraded", latency_ms: 1500, injection_score: null, ...over } });

test("when the injection model did not answer the verdict is Patterns only, never Clean, with n/a and an explanation", () => {
  render(<XRayDrawer {...props} msg={msg(patternsOnly())} />);
  const g = screen.getByRole("region", { name: "Guardrail" });
  expect(within(g).getByText("Patterns only")).toBeInTheDocument();
  expect(within(g).queryByText("Clean")).toBeNull();
  expect(within(g).getByText("Degraded")).toBeInTheDocument();
  expect(within(g).getByText("n/a")).toBeInTheDocument();
  expect(within(g).queryByText("0.00")).toBeNull();
  expect(within(g).getByText("The injection model did not answer, so only pattern checks ran.")).toBeInTheDocument();
  const word = within(g).getByText("Patterns only").closest("span")!;
  expect(word.className).toContain("text-on-ink-muted");
  expect(word.className).not.toContain("text-clean");
});

test("a flagged verdict without an injection score stays Flagged and shows n/a", () => {
  render(<XRayDrawer {...props} msg={msg(patternsOnly({ verdict: "FLAGGED", reasons: ["pii_email"] }))} />);
  const g = screen.getByRole("region", { name: "Guardrail" });
  expect(within(g).getByText("Flagged")).toBeInTheDocument();
  expect(within(g).getByText("n/a")).toBeInTheDocument();
  expect(within(g).queryByText(/did not answer/)).toBeNull();
});

test("a scored clean answer still reads Clean with its probability", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  const g = screen.getByRole("region", { name: "Guardrail" });
  expect(within(g).getByText("Clean")).toBeInTheDocument();
  expect(within(g).getByText("0.02")).toBeInTheDocument();
});

test("the LLM bar is blue (yellow is for cost only) and the guardrail bar follows the verdict", () => {
  const { container } = render(<XRayDrawer {...props} msg={msg(response())} />);
  const bars = Array.from(container.querySelectorAll("ol span.absolute"));
  expect(bars.some((b) => b.className.includes("bg-cost"))).toBe(false);
  expect(bars[0].className).toContain("bg-clean");
  expect(bars[3].className).toContain("bg-blue-bright");
});

test("the guardrail bar is neutral when only patterns ran", () => {
  const { container } = render(<XRayDrawer {...props} msg={msg(patternsOnly())} />);
  const bars = Array.from(container.querySelectorAll("ol span.absolute"));
  expect(bars[0].className).toContain("bg-on-ink-muted");
  expect(bars[0].className).not.toContain("bg-clean");
});

const flaggedResp = () => response({ blocked: true, docs: [], hidden: [], guardrail: { verdict: "FLAGGED", reasons: ["prompt_injection"], status: "ok", latency_ms: 41, injection_score: 0.97 } });
const sec = { securityKibanaUrl: "https://sec.example" };

test("a blocked prompt links to the Security alerts page, the trace, and explains where it was blocked", () => {
  render(<XRayDrawer {...props} {...sec} msg={msg(flaggedResp())} />);
  const alerts = screen.getByRole("link", { name: /view detection in elastic security/i });
  expect(alerts).toHaveAttribute("href", expect.stringContaining("https://sec.example/app/security/alerts?query="));
  expect(alerts).toHaveAttribute("target", "_blank");
  expect(alerts).toHaveAttribute("rel", "noreferrer noopener");
  expect(within(alerts).getByText(/opens in a new tab/i)).toHaveClass("sr-only");
  expect(screen.getByText(/detections run every minute/i)).toBeInTheDocument();
  const where = screen.getByRole("link", { name: /see where it was blocked/i });
  expect(where).toHaveAttribute("href", "https://kb.example/app/apm/link-to/trace/4bf92f3577b34da6a3ce929d0e0e4736");
  expect(screen.getByText((_, el) => el?.tagName === "P" && /^Blocked in guardrail\.check before retrieval and the LLM call\.$/.test(el.textContent ?? ""))).toBeInTheDocument();
});

test("a clean prompt has no detection links", () => {
  render(<XRayDrawer {...props} {...sec} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /view detection/i })).toBeNull();
  expect(screen.queryByRole("link", { name: /see where it was blocked/i })).toBeNull();
});

test("security links are hidden when the Security Kibana URL is null", () => {
  render(<XRayDrawer {...props} securityKibanaUrl={null} msg={msg(flaggedResp())} />);
  expect(screen.queryByRole("link", { name: /view detection/i })).toBeNull();
  expect(screen.queryByText(/detections run every/i)).toBeNull();
  expect(screen.getByRole("link", { name: /see where it was blocked/i })).toBeInTheDocument();
});

test("visible documents link to Discover with a note; hidden ghost cards get no link", () => {
  render(<XRayDrawer {...props} msg={msg(response())} />);
  const link = screen.getByRole("link", { name: /paid time off policy/i });
  expect(link).toHaveAttribute("href", expect.stringContaining("https://kb.example/app/discover#/?_a="));
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noreferrer noopener");
  expect(screen.getByText(/opens in kibana \(your kibana role applies, not the persona\)/i)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /project aurora/i })).toBeNull();
});

test("document titles are plain text without a Kibana URL", () => {
  render(<XRayDrawer {...props} kibanaUrl={undefined} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /paid time off policy/i })).toBeNull();
  expect(screen.getByText("Paid Time Off Policy")).toBeInTheDocument();
  expect(screen.queryByText(/your kibana role applies/i)).toBeNull();
});

test("the cost section links to the cost dashboard, hidden without a Kibana URL", () => {
  const { unmount } = render(<XRayDrawer {...props} msg={msg(response())} />);
  expect(screen.getByRole("link", { name: /open cost dashboard/i })).toHaveAttribute("href", "https://kb.example/app/dashboards#/view/glassbox-overview");
  unmount();
  render(<XRayDrawer {...props} kibanaUrl={undefined} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /open cost dashboard/i })).toBeNull();
});

const gr = { models: { injection: "inj__model", ner: "ner__model" }, pipeline: "genai-guardrail" };

test("Dev Tools link shows for clean and flagged verdicts, built from this message prompt", () => {
  const { unmount } = render(<XRayDrawer {...props} guardrailConfig={gr} msg={msg(response())} />);
  const link = within(screen.getByRole("region", { name: "Guardrail" })).getByRole("link", { name: /try it in dev tools/i });
  expect(link.getAttribute("href")).toMatch(/^https:\/\/kb\.example\/app\/dev_tools#\/console\?load_from=data:text\/plain,/);
  expect(within(screen.getByRole("region", { name: "Guardrail" })).getByText(/needs a kibana login/i)).toBeInTheDocument();
  unmount();
  render(<XRayDrawer {...props} guardrailConfig={gr} msg={msg(response({ guardrail: { verdict: "FLAGGED", reasons: ["pii_email"], status: "ok", latency_ms: 3, injection_score: 0.1 } }))} />);
  expect(within(screen.getByRole("region", { name: "Guardrail" })).getByRole("link", { name: /try it in dev tools/i })).toBeInTheDocument();
});

test("Dev Tools link is hidden without kibana url, guardrail config or prompt", () => {
  const { unmount } = render(<XRayDrawer {...props} kibanaUrl={undefined} guardrailConfig={gr} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /dev tools/i })).toBeNull();
  unmount();
  const u2 = render(<XRayDrawer {...props} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /dev tools/i })).toBeNull();
  u2.unmount();
  render(<XRayDrawer {...props} question={undefined} guardrailConfig={gr} msg={msg(response())} />);
  expect(screen.queryByRole("link", { name: /dev tools/i })).toBeNull();
});

test("an answered response shows Quality with its links and no checklist of untriggered checks", () => {
  render(<XRayDrawer {...props} qualityPipeline="genai-quality" msg={msg(response())} />);
  const q = screen.getByRole("region", { name: "Quality" });
  expect(within(q).getByText(/5 to 10 seconds/)).toBeInTheDocument();
  const dev = within(q).getByRole("link", { name: /try it in dev tools/i });
  const text = decompressFromEncodedURIComponent(dev.getAttribute("href")!.split("load_from=data:text/plain,")[1])!;
  expect(text).toContain("POST _ingest/pipeline/genai-quality/_simulate");
  expect(within(q).getByRole("link", { name: /open the response log/i }).getAttribute("href")).toContain("https://kb.example/app/discover#/?_a=");
  expect(within(q).getByRole("link", { name: /conversation quality dashboard/i })).toHaveAttribute("href", "https://kb.example/app/dashboards#/view/glassbox-quality");
  expect(within(q).queryByText("What Elastic checks on this answer")).toBeNull();
  expect(within(q).queryByRole("list")).toBeNull();
  expect(within(screen.getByRole("region", { name: "Security" })).getByRole("link", { name: /owasp coverage dashboard/i })).toHaveAttribute("href", "https://kb.example/app/dashboards#/view/glassbox-owasp");
  expect(within(q).getByText(/needs a kibana login/i)).toBeInTheDocument();
});

test("a blocked response says there is nothing to score under Quality", () => {
  render(<XRayDrawer {...props} qualityPipeline="genai-quality" msg={msg(response({ blocked: true, docs: [], hidden: [] }))} />);
  expect(within(screen.getByRole("region", { name: "Quality" })).getByText(/nothing to score/i)).toBeInTheDocument();
});

test("without a Kibana url the quality links are hidden; without the pipeline only Dev Tools is", () => {
  const { rerender } = render(<XRayDrawer {...props} kibanaUrl={undefined} qualityPipeline="genai-quality" msg={msg(response())} />);
  const q = () => screen.getByRole("region", { name: "Quality" });
  expect(within(q()).queryAllByRole("link")).toHaveLength(0);
  rerender(<XRayDrawer {...props} msg={msg(response())} />);
  expect(within(q()).queryByRole("link", { name: /dev tools/i })).toBeNull();
  expect(within(q()).getAllByRole("link")).toHaveLength(2);
});
