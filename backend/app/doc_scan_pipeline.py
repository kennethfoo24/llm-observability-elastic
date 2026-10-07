"""`genai-doc-scan` ingest pipeline: document integrity and poisoning scan (OWASP LLM04, indirect LLM01).

Used only for the separate demo index `hr-kb-staging` (the live `hr-kb` is never touched). Steps:
  1. fingerprint (SHA-256) over title + content + classification + allowed_roles -> doc_scan.fingerprint
  2. baseline: doc_scan.baseline_fingerprint is set ONCE (kept when the indexer carries the stored one, see
     scripts/poison_demo.py; otherwise it becomes the current fingerprint)
  3. chunk `content` into up to 4 chunks of 2000 chars (the DeBERTa max length is limited), run the injection
     classifier on each chunk and take the MAX P(injection)
  4. regex/painless phrase scan (instruction-like text aimed at a model, markup, hidden unicode) -> doc_scan.patterns
  5. verdict script -> doc_scan.verdict FLAGGED | CLEAN | UNKNOWN, doc_scan.reasons, doc_scan.injection_score,
     doc_scan.changed (fingerprint differs from baseline)
Model steps use ignore_failure; pipeline on_failure sets UNKNOWN."""
from .guardrail_pipeline import INJECTION_MODEL

PIPELINE_ID = "genai-doc-scan"
STAGING_INDEX = "hr-kb-staging"
CHUNK_SIZE = 2000
MAX_CHUNKS = 4
INJECTION_THRESHOLD = 0.85
FINGERPRINT_FIELDS = ["title", "content", "classification", "allowed_roles"]
TMP = "doc_scan_tmp"

_KW = {"type": "keyword"}
DOC_SCAN_MAPPINGS: dict = {"properties": {
    "fingerprint": _KW, "baseline_fingerprint": _KW,
    "verdict": _KW, "reasons": _KW, "patterns": _KW,
    "injection_score": {"type": "double"},
    "chunks_scanned": {"type": "integer"},
    "changed": {"type": "boolean"},
    "scanned_at": {"type": "date"},
}}


def index_body() -> dict:
    """hr-kb mapping (copied from index_def.INDEX_BODY) plus our typed result fields and @timestamp."""
    from .index_def import INDEX_BODY
    props = dict(INDEX_BODY["mappings"]["properties"])
    props["@timestamp"] = {"type": "date"}
    props["doc_scan"] = DOC_SCAN_MAPPINGS
    return {"mappings": {"properties": props}}


CHUNK_SCRIPT = r"""
String c = ctx.content == null ? '' : ctx.content.toString();
Map t = new HashMap();
int n = 0;
int size = (int) params.chunk_size;
int maxChunks = (int) params.max_chunks;
for (int i = 0; i < maxChunks; i++) {
  int from = i * size;
  if (from >= c.length()) { break; }
  int to = from + size;
  if (to > c.length()) { to = c.length(); }
  t['c' + i] = c.substring(from, to);
  n++;
}
t.n = n;
ctx.doc_scan_tmp = t;
"""

PATTERN_SCRIPT = r"""
Map t = ctx.doc_scan_tmp;
String s = ((ctx.title == null ? '' : ctx.title.toString()) + ' ' + (ctx.content == null ? '' : ctx.content.toString())).toLowerCase();
List p = new ArrayList();
if (/(?:ignore|forget|override)\s+(?:all\s+|any\s+|your\s+)?(?:the\s+)?(?:previous|prior|above|earlier)/.matcher(s).find()) { p.add('ignore_previous'); }
if (/disregard\s+(?:all\s+)?(?:of\s+)?the\s+(?:above|previous|prior)/.matcher(s).find()) { p.add('disregard_above'); }
if (/system\s+prompt/.matcher(s).find()) { p.add('system_prompt'); }
if (/you\s+must\s+now/.matcher(s).find()) { p.add('you_must_now'); }
if (/\breveal\b/.matcher(s).find()) { p.add('reveal'); }
if (s.contains('<script')) { p.add('script_tag'); }
if (/(?:email|send|forward|post)\b.{0,60}\b(?:password|credentials|api\s*key|secret)/.matcher(s).find()) { p.add('credential_exfiltration'); }
boolean hidden = false;
for (int i = 0; i < s.length(); i++) {
  int ch = (int) s.charAt(i);
  // U+E0000..E007F tag characters are the surrogate pair starting 0xDB40; zero width and BOM characters
  if (ch == 0xDB40 || ch == 0x200B || ch == 0x200C || ch == 0x200D || ch == 0x2060 || ch == 0xFEFF || ch == 0x180E) { hidden = true; break; }
}
if (hidden) { p.add('hidden_unicode'); }
t.patterns = p;
"""

VERDICT_SCRIPT = r"""
Map t = ctx.doc_scan_tmp;
if (t == null) { t = new HashMap(); }
int n = t.n == null ? 0 : ((Number) t.n).intValue();
double maxInj = 0.0;
int ok = 0;
for (int i = 0; i < n; i++) {
  def r = t['i' + i];
  if (r != null && r.predicted_value != null) {
    ok++;
    double pr = ((Number) r.prediction_probability).doubleValue();
    double pInj = r.predicted_value == 'INJECTION' ? pr : 1.0 - pr;
    if (pInj > maxInj) { maxInj = pInj; }
  }
}
boolean modelsOk = n > 0 && ok == n;
List reasons = new ArrayList();
if (maxInj >= params.injection_threshold) { reasons.add('prompt_injection'); }
List patterns = t.patterns == null ? new ArrayList() : t.patterns;
if (!patterns.isEmpty()) { reasons.add('instruction_patterns'); }
Map d = ctx.doc_scan;
if (d == null) { d = new HashMap(); ctx.doc_scan = d; }
boolean changed = d.fingerprint != null && d.baseline_fingerprint != null && !d.fingerprint.equals(d.baseline_fingerprint);
if (changed) { reasons.add('content_changed'); }
if (!modelsOk && reasons.isEmpty()) { reasons.add('model_unavailable'); }
boolean flagged = maxInj >= params.injection_threshold || !patterns.isEmpty();
d.verdict = flagged ? 'FLAGGED' : (modelsOk ? 'CLEAN' : 'UNKNOWN');
d.reasons = reasons;
d.patterns = patterns;
d.injection_score = maxInj;
d.chunks_scanned = ok;
d.changed = changed;
"""


def build_doc_scan_pipeline() -> dict:
    processors: list[dict] = [
        {"fingerprint": {"fields": FINGERPRINT_FIELDS, "target_field": "doc_scan.fingerprint",
                         "method": "SHA-256", "ignore_missing": True}},
        {"set": {"field": "doc_scan.baseline_fingerprint", "copy_from": "doc_scan.fingerprint", "override": False}},
        {"script": {"lang": "painless", "source": CHUNK_SCRIPT,
                    "params": {"chunk_size": CHUNK_SIZE, "max_chunks": MAX_CHUNKS}}},
    ]
    for i in range(MAX_CHUNKS):
        processors.append({"inference": {
            "model_id": INJECTION_MODEL, "target_field": f"{TMP}.i{i}",
            "field_map": {f"{TMP}.c{i}": "text_field"},
            "if": f"ctx.{TMP}?.c{i} != null", "ignore_failure": True}})
    processors += [
        {"script": {"lang": "painless", "source": PATTERN_SCRIPT}},
        {"script": {"lang": "painless", "source": VERDICT_SCRIPT, "params": {"injection_threshold": INJECTION_THRESHOLD}}},
        {"set": {"field": "doc_scan.scanned_at", "value": "{{{_ingest.timestamp}}}"}},
        {"set": {"field": "@timestamp", "value": "{{{_ingest.timestamp}}}"}},
        {"remove": {"field": TMP, "ignore_missing": True}},
    ]
    return {
        "description": "Document integrity and poisoning scan (OWASP LLM04, indirect LLM01) for the hr-kb-staging demo index",
        "processors": processors,
        "on_failure": [
            {"set": {"field": "doc_scan.verdict", "value": "UNKNOWN"}},
            {"set": {"field": "doc_scan.reasons", "value": ["pipeline_error"]}},
            {"set": {"field": "doc_scan.scanned_at", "value": "{{{_ingest.timestamp}}}"}},
            {"set": {"field": "@timestamp", "value": "{{{_ingest.timestamp}}}"}},
            {"remove": {"field": TMP, "ignore_missing": True, "ignore_failure": True}},
        ],
    }
