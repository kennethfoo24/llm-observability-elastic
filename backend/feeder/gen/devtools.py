"""Stage 3 generators, group `devtools`: NVIDIA GPU (DCGM style metrics), Cursor (audit log), GitLab (application logs)
and Slack (audit log). Everything is fabricated demo data: invented users, projects, hosts and GPUs.

Modules: devtools.py (this: catalog, topology, helpers), devtools_nvidia.py, devtools_cursor.py, devtools_gitlab.py,
devtools_slack.py. Each registers its generators with registry.register("devtools", ...).
"""
from __future__ import annotations

from .. import catalog

GROUP = "devtools"

catalog.register(
    catalog.pkg("nvidia_gpu", "0.4.1", GROUP, [("stats", "nvidia_gpu.stats", "metrics")]),
    catalog.pkg("nvidia_gpu_otel", "0.3.0", GROUP, []),          # content package (assets only)
    catalog.pkg("cursor", "0.2.2", GROUP, [("audit", "cursor.audit", "logs")]),
    catalog.pkg("gitlab", "3.1.0", GROUP, [
        ("api", "gitlab.api", "logs"), ("application", "gitlab.application", "logs"), ("audit", "gitlab.audit", "logs"),
        ("auth", "gitlab.auth", "logs"), ("pages", "gitlab.pages", "logs"), ("production", "gitlab.production", "logs"),
        ("sidekiq", "gitlab.sidekiq", "logs")]),
    catalog.pkg("slack", "1.32.0", GROUP, [("audit", "slack.audit", "logs")]),
)
S = {s.key: s for s in catalog.streams(GROUP)}


# ----- shared helpers (the `infra` module has the estate level helpers: counters, load rates, host and agent blocks) -------------
import functools  # noqa: E402
import json  # noqa: E402

from .. import engine  # noqa: E402,F401
from . import infra  # noqa: E402
from .infra import OtelStream, agent_block, host_block, stable  # noqa: E402,F401


@functools.lru_cache(maxsize=None)
def _tpl(key: str) -> dict:
    return json.loads(S[key].template_path.read_text())["sample"]


def sample(key: str) -> dict:
    """Deep copy of the committed sample event of a devtools stream."""
    return json.loads(json.dumps(_tpl(key)))


def J(o) -> str:
    return json.dumps(o, separators=(",", ":"))


def metric_base(key: str, host: str, module: str = "prometheus") -> dict:
    """Sample event re-hosted on a topology host (keeps the package's own structure, drops the sample's data)."""
    d = sample(key)
    d["host"] = host_block(host)
    d["agent"] = agent_block(host, "metricbeat")
    d.setdefault("event", {}).pop("ingested", None)
    d["event"].setdefault("module", module)
    d.pop("cloud", None)
    d.get("data_stream", {}).pop("namespace", None)
    return d
