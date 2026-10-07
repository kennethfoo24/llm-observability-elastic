from datetime import datetime, timedelta, timezone

import pytest

from elastic.client import Project
from elastic.dashboards.panels import OWASP_DASHBOARD, QUALITY_DASHBOARD
from elastic.rules import quality_alerts

pytestmark = pytest.mark.integration
NEW_PANELS = [*QUALITY_DASHBOARD.panels, *OWASP_DASHBOARD.panels]


@pytest.fixture(scope="module")
def obs():
    return Project("observability")


@pytest.mark.parametrize("panel", NEW_PANELS, ids=[p.title for p in NEW_PANELS])
def test_new_panel_esql_runs_live(obs, panel):
    end = datetime.now(timezone.utc)
    body = {"query": panel.esql, "params": [{"_tstart": (end - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                                            {"_tend": end.strftime("%Y-%m-%dT%H:%M:%SZ")}]}
    status, resp = obs.es("POST", "/_query", body)
    assert status == 200, (panel.title, str(resp)[:300])
    names = [c["name"] for c in resp["columns"]]
    assert panel.y in names and panel.x in names, names


@pytest.mark.parametrize("rule_id", sorted(quality_alerts.BY_ID))
def test_quality_alert_query_runs_live(obs, rule_id):
    status, resp = obs.es("POST", "/_query", {"query": quality_alerts.rule_body(rule_id)["params"]["esqlQuery"]["esql"]})
    assert status == 200 and isinstance(resp["columns"], list) and resp["columns"], str(resp)[:300]
