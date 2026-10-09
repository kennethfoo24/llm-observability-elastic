"""Stage 4a generators, group `rest`: system (Linux auth, Windows Security), Palo Alto (panw), Cisco (asa, meraki),
NetFlow and PostgreSQL (logs and the OTel receiver data).

Modules: rest.py (this: catalog, topology, helpers), rest_panw.py, rest_cisco.py, rest_netflow.py, rest_postgres.py,
rest_system.py. Real data of other demos already lives in several of these streams (panw, cisco, netflow, system); the
synthetic documents only add what the dashboards miss and are tagged like every feeder document.
"""
from __future__ import annotations

import hashlib

from .. import catalog, engine
from .infra import OtelStream, agent_block, host_block, stable  # noqa: F401  (re-exported for the rest modules)

GROUP = "rest"

catalog.register(
    catalog.pkg("panw", "5.5.0", GROUP, [("panos", "panw.panos", "logs")]),
    catalog.pkg("cisco_asa", "2.45.11", GROUP, [("log", "cisco_asa.log", "logs")]),
    catalog.pkg("cisco_meraki", "1.31.1", GROUP, [("log", "cisco_meraki.log", "logs")]),
    catalog.pkg("netflow", "2.25.1", GROUP, [("log", "netflow.log", "logs")]),
    catalog.pkg("postgresql", "1.32.1", GROUP, [("log", "postgresql.log", "logs")]),
    catalog.pkg("system", "2.23.0", GROUP, [("auth", "system.auth", "logs"), ("security", "system.security", "logs"),
                                              ("memory", "system.memory", "metrics")]),
    # content packages with no data streams of their own (assets only)
    catalog.pkg("postgresql_otel", "0.5.0", GROUP, []),
    catalog.pkg("system_otel", "0.3.0", GROUP, []),
)
S = {s.key: s for s in catalog.streams(GROUP)}
# system.memory is a TSDB metrics data stream in the project (custom _id refused); registered like the infra ones
engine.NO_ID_PREFIXES.append("metrics-system.memory-")


def uid(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
