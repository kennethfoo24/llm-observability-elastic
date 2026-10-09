"""NetFlow (netflow.log): flow records shaped like the Filebeat netflow input output, so the package pipeline adds the
community id and, for the PUBLIC addresses used here, the geo location and the autonomous system (source and destination)
that the real private-address demo flows never get. Adds `netflow.vlan_id` too (missing in the existing data).
"""
from __future__ import annotations

import base64
import hashlib
from datetime import timedelta

from .. import registry
from ..registry import Ctx, Generator
from . import rest

S = rest.S["netflow/log"]
# public addresses with an AS organization and a country (and often a city) in the GeoLite2 databases
PUBLIC = ["8.8.8.8", "52.95.110.1", "13.107.42.14", "151.101.1.69", "31.13.71.36", "17.253.144.10", "140.82.112.3", "81.2.69.142", "89.160.20.112",
          "175.16.199.0", "216.160.83.56", "2.125.160.216", "128.101.101.101", "185.60.216.35", "20.190.151.1", "3.5.140.1", "58.246.0.1", "103.28.54.1",
          "24.24.24.24", "23.32.0.1", "199.232.0.1", "192.0.78.24", "54.239.28.85", "124.64.0.1", "41.0.0.1", "5.255.255.5", "46.4.0.1", "62.0.0.1",
          "80.0.0.1", "78.0.0.1", "91.0.0.1", "94.0.0.1", "142.250.190.78", "202.89.233.100"]
EXPORTERS = [("10.20.1.28", 41391), ("10.20.1.29", 45073)]
VLANS = [10, 20, 30, 100, 200]
SERVICES = [(443, 6, 0.55), (80, 6, 0.12), (53, 17, 0.1), (22, 6, 0.04), (3389, 6, 0.02), (123, 17, 0.04), (8443, 6, 0.05), (25, 6, 0.02), (445, 6, 0.02),
            (5060, 17, 0.02), (1194, 17, 0.02)]


def _flow(c: Ctx) -> dict:
    r = c.rng
    ex_ip, ex_port = EXPORTERS[r.randrange(len(EXPORTERS))]
    inside = f"10.10.{r.randrange(1, 12)}.{r.randrange(2, 250)}"
    pub = r.choice(PUBLIC)
    port, proto = r.choices([(p, pr) for p, pr, _ in SERVICES], weights=[w for _, _, w in SERVICES])[0]
    outbound = r.random() < 0.7
    sip, dip = (inside, pub) if outbound else (pub, inside)
    sport, dport = (r.randrange(1024, 65000), port) if outbound else (port, r.randrange(1024, 65000))
    octets = int(r.lognormvariate(8.2, 1.6)) + 40
    packets = max(1, octets // r.randrange(300, 1200))
    dur_ms = int(r.lognormvariate(6.0, 1.3))
    up = 400_000_000 + int(c.ts.timestamp()) % 100_000_000 * 3
    flow_id = base64.b64encode(hashlib.sha256(f"{c.ts}{c.i}{sip}{dip}".encode()).digest()[:8]).decode().rstrip("=").replace("+", "A").replace("/", "B")
    start = c.ts - timedelta(milliseconds=dur_ms)
    d = {"input": {"type": "netflow"},
         "event": {"action": "netflow_flow", "category": ["network"], "kind": "event", "type": ["connection"],
                   "start": start.strftime("%Y-%m-%dT%H:%M:%S.") + f"{start.microsecond // 1000:03d}Z", "end": c.ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{c.ts.microsecond // 1000:03d}Z"},
         "flow": {"id": flow_id, "locality": "external"},
         "netflow": {"destination_ipv4_address": dip, "destination_transport_port": dport, "source_ipv4_address": sip, "source_transport_port": sport,
                     "octet_delta_count": octets, "packet_delta_count": packets, "protocol_identifier": proto, "type": "netflow_flow", "vlan_id": r.choice(VLANS),
                     "ingress_interface": r.randrange(1, 5), "egress_interface": r.randrange(5, 9), "ip_class_of_service": r.choice([0, 0, 0, 32, 40]),
                     "tcp_control_bits": r.choice([2, 16, 18, 24, 25]) if proto == 6 else 0,
                     "flow_start_sys_up_time": up - dur_ms, "flow_end_sys_up_time": up,
                     "exporter": {"address": f"{ex_ip}:{ex_port}", "source_id": 1, "version": 9, "uptime_millis": up,
                                  "timestamp": c.ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{c.ts.microsecond // 1000:03d}Z"}},
         "network": {"bytes": octets, "packets": packets, "direction": "outbound" if outbound else "inbound", "iana_number": str(proto),
                     "transport": "tcp" if proto == 6 else "udp", "type": "ipv4"},
         "observer": {"ip": ex_ip},
         "source": {"ip": sip, "port": sport, "bytes": octets, "packets": packets, "locality": "internal" if outbound else "external"},
         "destination": {"ip": dip, "port": dport, "locality": "external" if outbound else "internal"},
         "tags": ["netflow", "forwarded"]}
    return d


registry.register(rest.GROUP, Generator(S, _flow, rate_per_min=2.0))
