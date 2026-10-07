import { alertsUrl, costDashboardUrl, docDiscoverUrl, rison, traceUrl } from "./kibanaLinks";

test("rison quotes strings and escapes quote and bang", () => {
  expect(rison("a b")).toBe("'a b'");
  expect(rison("it's!")).toBe("'it!'s!!'");
});

test("traceUrl encodes the trace id", () => {
  expect(traceUrl("https://kb", "ab/c")).toBe("https://kb/app/apm/link-to/trace/ab%2Fc");
});

test("alertsUrl filters the alerts page to the detection rule with a kuery rison query", () => {
  const u = alertsUrl("https://sec");
  expect(u.startsWith("https://sec/app/security/alerts?query=")).toBe(true);
  const q = decodeURIComponent(u.split("query=")[1].split("&")[0]);
  expect(q).toBe(`(language:kuery,query:'kibana.alert.rule.rule_id : "glassbox-flagged-prompts"')`);
  expect(u).toContain("timerange=");
});

test("docDiscoverUrl builds an ES|QL Discover link on hr-kb by _id", () => {
  const u = docDiscoverUrl("https://kb", "pto-policy");
  expect(u.startsWith("https://kb/app/discover#/?_a=")).toBe(true);
  const a = decodeURIComponent(u.split("_a=")[1]);
  expect(a).toBe(`(dataSource:(type:esql),query:(esql:'FROM hr-kb METADATA _id | WHERE _id == "pto-policy"'))`);
});

test("docDiscoverUrl escapes quotes, backslashes and url-special characters in ids", () => {
  const u = docDiscoverUrl("https://kb", `a"b\\c'd&e#f`);
  expect(u).not.toMatch(/[&#].*[&#]/);
  const a = decodeURIComponent(u.split("_a=")[1]);
  expect(a).toContain(`WHERE _id == "a\\"b\\\\c!'d&e#f"`);
});

test("costDashboardUrl opens the glassbox-overview dashboard", () => {
  expect(costDashboardUrl("https://kb")).toBe("https://kb/app/dashboards#/view/glassbox-overview");
});

import { decompressFromEncodedURIComponent } from "lz-string";
import { devToolsConsoleText, devToolsUrl, MAX_DEVTOOLS_URL_CHARS } from "./kibanaLinks";

const GR = { models: { injection: "inj__model", ner: "ner__model" }, pipeline: "pipe-id" };
const payload = (url: string) => decompressFromEncodedURIComponent(url.split("load_from=data:text/plain,")[1]);

test("devToolsUrl uses the Console share format and round-trips", () => {
  const url = devToolsUrl("https://kb", "hello", GR);
  expect(url.startsWith("https://kb/app/dev_tools#/console?load_from=data:text/plain,")).toBe(true);
  expect(payload(url)).toBe(devToolsConsoleText("hello", GR));
});

test("console text holds the three requests with model ids and pipeline from config", () => {
  const t = devToolsConsoleText("hello", GR);
  expect(t).toContain("POST _ml/trained_models/inj__model/_infer");
  expect(t).toContain("POST _ml/trained_models/ner__model/_infer");
  expect(t).toContain("POST _ingest/pipeline/pipe-id/_simulate");
  const bodies = t.split("\n\n").map((b) => b.split("\n").filter((l) => !l.startsWith("#") && !/^POST /.test(l)).join("\n"));
  expect(JSON.parse(bodies[0])).toEqual({ docs: [{ text_field: "hello" }] });
  expect(JSON.parse(bodies[1])).toEqual({ docs: [{ text_field: "hello" }] });
  expect(JSON.parse(bodies[2])).toEqual({ docs: [{ _source: { attributes: { "genai.prompt_text": "hello" }, data_stream: { dataset: "genai_guardrail" } } }] });
});

test("quotes, newlines and unicode are escaped so each body stays valid JSON", () => {
  const prompt = 'say "hi"\nline two \\ café 你好 😀';
  const t = payload(devToolsUrl("https://kb", prompt, GR))!;
  const bodies = t.split("\n\n").map((b) => b.split("\n").filter((l) => !l.startsWith("#") && !/^POST /.test(l)).join("\n"));
  expect(JSON.parse(bodies[0]).docs[0].text_field).toBe(prompt);
  expect(JSON.parse(bodies[2]).docs[0]._source.attributes["genai.prompt_text"]).toBe(prompt);
});

test("very long prompts are truncated to fit the URL and say so in the console text", () => {
  let seed = 7;
  const long = Array.from({ length: 20000 }, () => { seed = (seed * 1103515245 + 12345) % 2147483648; return String.fromCharCode(33 + (seed >> 8) % 90); }).join("");
  const url = devToolsUrl("https://kb", long, GR);
  expect(url.length).toBeLessThanOrEqual(MAX_DEVTOOLS_URL_CHARS);
  const t = payload(url)!;
  expect(t).toMatch(/^# Prompt truncated/);
  expect(t.length).toBeLessThan(long.length);
});

test("short prompts have no truncation note", () => {
  expect(payload(devToolsUrl("https://kb", "short", GR))).not.toContain("truncated");
});

import { owaspDashboardUrl, qualityConsoleText, qualityDashboardUrl, qualityDevToolsUrl, responseLogUrl, type QualityInput } from "./kibanaLinks";

const QI: QualityInput = { prompt: "How many PTO days?", response: "25 days [pto-policy]", context: "[pto-policy] Paid Time Off Policy",
  citedIds: ["pto-policy"], retrievedIds: ["pto-policy"], topScore: 3.2, hiddenCount: 1, answered: true, persona: "employee" };
const jsonBody = (t: string) => JSON.parse(t.split("\n").filter((l) => !l.startsWith("#") && !/^POST /.test(l)).join("\n"));

test("dashboard links open the quality and OWASP dashboards", () => {
  expect(qualityDashboardUrl("https://kb")).toBe("https://kb/app/dashboards#/view/glassbox-quality");
  expect(owaspDashboardUrl("https://kb")).toBe("https://kb/app/dashboards#/view/glassbox-owasp");
});

test("responseLogUrl builds an ES|QL Discover link on the genai_response logs by trace id", () => {
  const u = responseLogUrl("https://kb", "abc123");
  expect(u.startsWith("https://kb/app/discover#/?_a=")).toBe(true);
  expect(decodeURIComponent(u.split("_a=")[1])).toBe(`(dataSource:(type:esql),query:(esql:'FROM logs-genai_response* | WHERE trace_id == "abc123"'))`);
});

test("responseLogUrl escapes quotes and url-special characters in the trace id", () => {
  const u = responseLogUrl("https://kb", `a"b'c&d#e`);
  expect(u).not.toMatch(/[&#].*[&#]/);
  expect(decodeURIComponent(u.split("_a=")[1])).toContain(`WHERE trace_id == "a\\"b!'c&d#e"`);
});

test("quality console text simulates the pipeline with the flat attributes the app logs", () => {
  const t = qualityConsoleText(QI, "genai-quality");
  expect(t).toContain("POST _ingest/pipeline/genai-quality/_simulate");
  expect(jsonBody(t)).toEqual({ docs: [{ _source: { attributes: {
    "genai.prompt_text": "How many PTO days?", "genai.response_text": "25 days [pto-policy]", "genai.context_text": "[pto-policy] Paid Time Off Policy",
    "genai.cited_ids": ["pto-policy"], "genai.retrieved_ids": ["pto-policy"], "genai.top_score": 3.2, "genai.hidden_count": 1,
    "genai.answered": true, "app.persona": "employee" }, data_stream: { dataset: "genai_response" } } }] });
});

test("qualityDevToolsUrl uses the Console share format and round-trips", () => {
  const url = qualityDevToolsUrl("https://kb", QI, "genai-quality");
  expect(url.startsWith("https://kb/app/dev_tools#/console?load_from=data:text/plain,")).toBe(true);
  expect(decompressFromEncodedURIComponent(url.split("load_from=data:text/plain,")[1])).toBe(qualityConsoleText(QI, "genai-quality"));
});

test("quotes, newlines and unicode in the answer keep the body valid JSON", () => {
  const q = { ...QI, response: 'say "hi"\nline \\ café 你好 😀' };
  const t = decompressFromEncodedURIComponent(qualityDevToolsUrl("https://kb", q, "p").split("load_from=data:text/plain,")[1])!;
  expect(jsonBody(t).docs[0]._source.attributes["genai.response_text"]).toBe(q.response);
});

test("very long texts are truncated to fit the URL and say so", () => {
  let seed = 11;
  const long = () => Array.from({ length: 15000 }, () => { seed = (seed * 1103515245 + 12345) % 2147483648; return String.fromCharCode(33 + (seed >> 8) % 90); }).join("");
  const url = qualityDevToolsUrl("https://kb", { ...QI, prompt: long(), response: long(), context: long() }, "genai-quality");
  expect(url.length).toBeLessThanOrEqual(MAX_DEVTOOLS_URL_CHARS);
  const t = decompressFromEncodedURIComponent(url.split("load_from=data:text/plain,")[1])!;
  expect(t).toMatch(/^# Texts truncated/);
  expect(jsonBody(t).docs[0]._source.attributes["genai.cited_ids"]).toEqual(["pto-policy"]);
});

test("short texts have no truncation note", () => {
  expect(decompressFromEncodedURIComponent(qualityDevToolsUrl("https://kb", QI, "p").split("load_from=data:text/plain,")[1])).not.toContain("truncated");
});
