import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.guardrail_pipeline import PIPELINE_ID, build_hook, build_pipeline  # noqa: E402

from elastic.client import Project  # noqa: E402
from elastic.dashboards.build import DASHBOARD_ID, build_ndjson  # noqa: E402
from elastic.dashboards.panels import PANELS  # noqa: E402
from elastic.rules import cost_alert, guardrail_detection  # noqa: E402

HOOK_PIPELINE = "logs@custom"
DASH_DIR = ROOT / "elastic" / "dashboards"


def _say(msg: str, dry: bool = False) -> None:
    print(msg + (" (dry run)" if dry else ""), flush=True)


def _fail(what: str, status, body) -> None:
    raise SystemExit(f"{what} failed: HTTP {status} {str(body)[:300]}")


def _put_pipelines(p: Project, dry: bool) -> None:
    _say(f"[{p.name}] pipeline {PIPELINE_ID}: put", dry)
    if not dry:
        status, body = p.es("PUT", f"/_ingest/pipeline/{PIPELINE_ID}", build_pipeline())
        if status != 200:
            _fail("pipeline put", status, body)
    status, existing = p.es("GET", f"/_ingest/pipeline/{HOOK_PIPELINE}")
    current = None
    if status == 200 and isinstance(existing, dict) and HOOK_PIPELINE in existing:
        current = {k: v for k, v in existing[HOOK_PIPELINE].items()
                   if k not in ("created_date_millis", "modified_date_millis")
                   and not (k.startswith("_") and k != "_meta")}
    merged = build_hook(current)
    n_before = len((current or {}).get("processors", []))
    _say(f"[{p.name}] hook {HOOK_PIPELINE}: processors {n_before} -> {len(merged['processors'])}", dry)
    if not dry and merged != current:
        status, body = p.es("PUT", f"/_ingest/pipeline/{HOOK_PIPELINE}", merged)
        if status != 200:
            _fail("hook put", status, body)


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
    body = guardrail_detection.rule_body()
    status, _ = p.kb("GET", f"/api/detection_engine/rules?rule_id={body['rule_id']}")
    exists = status == 200
    _say(f"[{p.name}] detection rule {body['rule_id']}: {'update' if exists else 'create'}", dry)
    if not dry:
        status, resp = p.kb("PUT" if exists else "POST", "/api/detection_engine/rules", body)
        if status not in (200, 201):
            _fail("detection rule upsert", status, resp)


def _import_dashboard(p: Project, dry: bool) -> None:
    ndjson = build_ndjson(PANELS, json.loads((DASH_DIR / "template.lens-esql.json").read_text()),
                          json.loads((DASH_DIR / "template.meta.json").read_text()))
    _say(f"[{p.name}] dashboard {DASHBOARD_ID}: import overwrite, {len(PANELS)} panels", dry)
    if not dry:
        status, text = p.kb_import(ndjson)
        if status != 200 or '"success":true' not in text.replace(" ", ""):
            _fail("dashboard import", status, text)


def apply_project(p: Project, cost_threshold: float, dry_run: bool) -> None:
    _put_pipelines(p, dry_run)
    if p.name == "observability":
        _upsert_rule(p, cost_alert.RULE_ID, cost_alert.rule_body(cost_threshold), dry_run)
        _import_dashboard(p, dry_run)
    if p.name == "security":
        _upsert_detection(p, dry_run)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", choices=["observability", "security", "all"], default="all")
    ap.add_argument("--cost-threshold", type=float, default=0.25)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for name in (["observability", "security"] if a.project == "all" else [a.project]):
        apply_project(Project(name), a.cost_threshold, a.dry_run)


if __name__ == "__main__":
    main()
