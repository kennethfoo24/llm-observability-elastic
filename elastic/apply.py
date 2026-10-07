import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.guardrail_pipeline import PIPELINE_ID, build_hook, build_pipeline  # noqa: E402

from app.quality_pipeline import PIPELINE_ID as QUALITY_PIPELINE_ID  # noqa: E402
from app.quality_pipeline import build_quality_hook, build_quality_pipeline  # noqa: E402

from elastic.client import Project  # noqa: E402
from elastic.dashboards.build import build_ndjson  # noqa: E402
from elastic.dashboards.panels import DASHBOARDS  # noqa: E402
from app.doc_scan_pipeline import PIPELINE_ID as DOC_SCAN_PIPELINE_ID  # noqa: E402
from app.doc_scan_pipeline import STAGING_INDEX, build_doc_scan_pipeline, index_body  # noqa: E402

from elastic.rules import cost_alert, doc_integrity, guardrail_detection, owasp_detections, quality_alerts  # noqa: E402
from elastic.templates import (  # noqa: E402
    COMPONENT_NAME, DEFAULT_TEMPLATE, INDEX_TEMPLATE_NAME, build_component, build_index_template)

HOOK_PIPELINE = "logs@custom"
DASH_DIR = ROOT / "elastic" / "dashboards"
CANARY_FILE = ROOT / "backend" / "secrets" / "system_prompt_canary.txt"


def read_canary(path: Path = CANARY_FILE) -> str:
    """The deploy-time canary (gitignored). Empty when absent: the pipeline then skips the leak check."""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _say(msg: str, dry: bool = False) -> None:
    print(msg + (" (dry run)" if dry else ""), flush=True)


def _fail(what: str, status, body) -> None:
    raise SystemExit(f"{what} failed: HTTP {status} {str(body)[:300]}")


def _put_templates(p: Project, dry: bool) -> None:
    status, body = p.es("GET", f"/_index_template/{DEFAULT_TEMPLATE}")   # read-only: copy its composed_of
    if status != 200 or not isinstance(body, dict) or not body.get("index_templates"):
        _fail("default otel template get", status, body)
    default = body["index_templates"][0]["index_template"]
    template = build_index_template(default)
    _say(f"[{p.name}] component template {COMPONENT_NAME}: put", dry)
    _say(f"[{p.name}] index template {INDEX_TEMPLATE_NAME}: put ({len(template['composed_of'])} components)", dry)
    if dry:
        return
    status, resp = p.es("PUT", f"/_component_template/{COMPONENT_NAME}", build_component())
    if status != 200:
        _fail("component template put", status, resp)
    status, resp = p.es("PUT", f"/_index_template/{INDEX_TEMPLATE_NAME}", template)
    if status != 200:
        _fail("index template put", status, resp)


def _put_pipelines(p: Project, dry: bool, quality_only: bool = False) -> None:
    canary = read_canary()
    if not quality_only:
        _say(f"[{p.name}] pipeline {PIPELINE_ID}: put", dry)
    _say(f"[{p.name}] pipeline {QUALITY_PIPELINE_ID}: put (canary {'set' if canary else 'EMPTY, leak check skipped'})", dry)
    if not dry:
        if not quality_only:
            status, body = p.es("PUT", f"/_ingest/pipeline/{PIPELINE_ID}", build_pipeline())
            if status != 200:
                _fail("pipeline put", status, body)
        status, body = p.es("PUT", f"/_ingest/pipeline/{QUALITY_PIPELINE_ID}",
                            build_quality_pipeline(p.name, canary))
        if status != 200:
            _fail("quality pipeline put", status, body)
    status, existing = p.es("GET", f"/_ingest/pipeline/{HOOK_PIPELINE}")
    current = None
    if status not in (200, 404):  # only 404 means "no hook yet"; anything else must not lead to a blind PUT
        _fail("hook get", status, existing)
    if status == 200 and isinstance(existing, dict) and HOOK_PIPELINE in existing:
        current = {k: v for k, v in existing[HOOK_PIPELINE].items()
                   if k not in ("created_date_millis", "modified_date_millis")
                   and not (k.startswith("_") and k != "_meta")}
    merged = build_quality_hook(build_hook(current))
    n_before = len((current or {}).get("processors", []))
    _say(f"[{p.name}] hook {HOOK_PIPELINE}: processors {n_before} -> {len(merged['processors'])}", dry)
    if not dry and merged != current:
        status, body = p.es("PUT", f"/_ingest/pipeline/{HOOK_PIPELINE}", merged)
        if status != 200:
            _fail("hook put", status, body)


def _put_doc_scan(p: Project, dry: bool) -> None:
    """genai-doc-scan pipeline plus the NEW staging index (created only when absent). hr-kb is never touched."""
    _say(f"[{p.name}] pipeline {DOC_SCAN_PIPELINE_ID}: put", dry)
    if not dry:
        status, body = p.es("PUT", f"/_ingest/pipeline/{DOC_SCAN_PIPELINE_ID}", build_doc_scan_pipeline())
        if status != 200:
            _fail("doc scan pipeline put", status, body)
    status, _ = p.es("GET", f"/{STAGING_INDEX}/_count")
    exists = status == 200
    _say(f"[{p.name}] index {STAGING_INDEX}: {'exists, kept' if exists else 'create'}", dry)
    if not dry and not exists:
        status, body = p.es("PUT", f"/{STAGING_INDEX}", index_body())
        if status != 200:
            _fail("staging index create", status, body)


def _upsert_rule(p: Project, rule_id: str, body: dict, dry: bool) -> None:
    path = f"/api/alerting/rule/{rule_id}"
    status, _ = p.kb("GET", path)
    exists = status == 200
    _say(f"[{p.name}] rule {rule_id}: {'update' if exists else 'create'}", dry)
    if dry:
        return
    status, resp = p.kb("PUT" if exists else "POST", path, cost_alert.update_body(body) if exists else body)
    if status not in (200, 201):
        _fail("rule upsert", status, resp)


def _upsert_detection(p: Project, dry: bool) -> None:
    for body in [guardrail_detection.rule_body(), *owasp_detections.rule_bodies()]:
        status, _ = p.kb("GET", f"/api/detection_engine/rules?rule_id={body['rule_id']}")
        exists = status == 200
        _say(f"[{p.name}] detection rule {body['rule_id']}: {'update' if exists else 'create'}", dry)
        if not dry:
            status, resp = p.kb("PUT" if exists else "POST", "/api/detection_engine/rules", body)
            if status not in (200, 201):
                _fail("detection rule upsert", status, resp)


def _import_dashboards(p: Project, dry: bool) -> None:
    template = json.loads((DASH_DIR / "template.lens-esql.json").read_text())
    meta = json.loads((DASH_DIR / "template.meta.json").read_text())
    for d in DASHBOARDS:
        ndjson = build_ndjson(list(d.panels), template, meta, d)
        _say(f"[{p.name}] dashboard {d.id}: import overwrite, {len(d.panels)} panels", dry)
        if not dry:
            status, result = p.kb_import(ndjson)
            if status != 200 or not isinstance(result, dict) or result.get("success") is not True:
                errors = result.get("errors") if isinstance(result, dict) else result
                _fail("dashboard import", status, errors)


def apply_project(p: Project, cost_threshold: float, dry_run: bool, only_quality: bool = False,
                  alert_overrides: dict[str, float] | None = None) -> None:
    _put_templates(p, dry_run)
    _put_pipelines(p, dry_run, only_quality)
    if only_quality:
        return
    if p.name == "observability":
        _upsert_rule(p, cost_alert.RULE_ID, cost_alert.rule_body(cost_threshold), dry_run)
        for rid, body in quality_alerts.all_rules(alert_overrides).items():
            _upsert_rule(p, rid, body, dry_run)
        _put_doc_scan(p, dry_run)
        _upsert_rule(p, doc_integrity.RULE_ID, doc_integrity.rule_body(), dry_run)
        _import_dashboards(p, dry_run)
    if p.name == "security":
        _upsert_detection(p, dry_run)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", choices=["observability", "security", "all"], required=True)
    ap.add_argument("--cost-threshold", type=float, default=0.25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-quality", action="store_true",
                    help="only the genai-quality templates, pipeline and logs@custom hook (no rules or dashboards)")
    ap.add_argument("--alert-override", action="append", default=[], metavar="RULE_ID=VALUE",
                    help="proof only: temporarily set one quality alert threshold (re-run without it to restore)")
    a = ap.parse_args()
    overrides = {k: float(v) for k, v in (x.split("=", 1) for x in a.alert_override)}
    unknown = set(overrides) - set(quality_alerts.BY_ID)
    if unknown:
        raise SystemExit(f"unknown alert id: {sorted(unknown)}")
    for name in (["observability", "security"] if a.project == "all" else [a.project]):
        apply_project(Project(name), a.cost_threshold, a.dry_run, a.only_quality, overrides)


if __name__ == "__main__":
    main()
