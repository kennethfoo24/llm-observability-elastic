// Pure Kibana deep-link builders. Base URLs come from /api/config, never from source.
// Kibana keeps app state in the URL as rison (the same format its Share menu produces).

export const DETECTION_RULE_ID = "glassbox-flagged-prompts";
export const DASHBOARD_ID = "glassbox-overview";

/** Rison string: single quoted, with ! escaping ' and !. */
export function rison(s: string): string {
  return `'${s.replace(/!/g, "!!").replace(/'/g, "!'")}'`;
}

export function traceUrl(base: string, traceId: string): string {
  return `${base}/app/apm/link-to/trace/${encodeURIComponent(traceId)}`;
}

/** Security alerts page filtered to the Glass Box detection rule, last 24 hours. */
export function alertsUrl(base: string): string {
  const query = `(language:kuery,query:${rison(`kibana.alert.rule.rule_id : "${DETECTION_RULE_ID}"`)})`;
  const timerange = `(global:(linkTo:!(),timerange:(from:now-24h,kind:relative,to:now)))`;
  return `${base}/app/security/alerts?query=${encodeURIComponent(query)}&timerange=${encodeURIComponent(timerange)}`;
}

/** Discover in ES|QL mode showing one hr-kb document (the retriever's hit id is the Elasticsearch _id). */
export function docDiscoverUrl(base: string, docId: string): string {
  const quoted = `"${docId.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  const esql = `FROM hr-kb METADATA _id | WHERE _id == ${quoted}`;
  const a = `(dataSource:(type:esql),query:(esql:${rison(esql)}))`;
  return `${base}/app/discover#/?_a=${encodeURIComponent(a)}`;
}

export function costDashboardUrl(base: string): string {
  return `${base}/app/dashboards#/view/${DASHBOARD_ID}`;
}
