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
