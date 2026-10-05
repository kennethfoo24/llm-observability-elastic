import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from elastic.client import Project
from elastic.dashboards.panels import PANELS

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def obs():
    return Project("observability")


@pytest.mark.parametrize("panel", PANELS, ids=[p.title for p in PANELS])
def test_panel_esql_runs_against_live_observability(obs, panel):
    end = datetime.now(timezone.utc)
    body = {"query": panel.esql,
            "params": [{"_tstart": (end - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                       {"_tend": end.strftime("%Y-%m-%dT%H:%M:%SZ")}]}
    status, resp = obs.es("POST", "/_query", body)
    assert status == 200, (panel.title, str(resp)[:300])
    names = [c["name"] for c in resp["columns"]]
    assert panel.y in names and panel.x in names, names


def test_cost_alert_query_runs(obs):
    from elastic.rules.cost_alert import rule_body
    status, resp = obs.es("POST", "/_query", {"query": rule_body(0.25)["params"]["esqlQuery"]["esql"]})
    assert status == 200 and isinstance(resp["columns"], list), str(resp)[:300]


def test_apply_all_dry_run_exits_zero():
    r = subprocess.run([sys.executable, "-m", "elastic.apply", "--project", "all", "--dry-run"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-300:]
