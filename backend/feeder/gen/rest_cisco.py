"""Cisco ASA (cisco_asa.log) and Cisco Meraki (cisco_meraki.log) as RAW syslog lines through the package pipelines.

Both streams already hold real data of other demos; these documents fill what the dashboards miss: ASA `event.original`
(Top ASA Messages) and the Meraki Air Marshal events (source.mac, rogue SSID and SSID spoofing counters).
"""
from __future__ import annotations

from datetime import datetime

from .. import registry
from ..registry import Ctx, Generator
from . import rest

ASA = rest.S["cisco_asa/log"]
MER = rest.S["cisco_meraki/log"]
ASA_HOSTS = ["asa-edge-01", "asa-edge-02"]
EXT = ["203.0.113.87", "198.51.100.7", "198.51.100.9", "192.0.2.44", "203.0.113.134", "8.8.8.8", "1.1.1.1"]
INT = [f"10.10.5.{n}" for n in range(20, 40)] + [f"10.20.5.{n}" for n in range(10, 14)]


def _asa_ts(ts: datetime) -> str:
    return f"{ts:%b} {ts.day:02d} {ts.year} {ts:%H:%M:%S}"


def _asa(c: Ctx) -> dict:
    r = c.rng
    host = ASA_HOSTS[r.randrange(2)]
    ext, inside, port = r.choice(EXT), r.choice(INT), r.choice([443, 443, 80, 22, 3389, 53, 8443])
    cid, sp = r.randrange(10000, 999999), r.randrange(1024, 65000)
    tpl = r.choices([
        (6, 302013, f"Built inbound TCP connection {cid} for outside:{ext}/{sp} ({ext}/{sp}) to inside:{inside}/{port} ({inside}/{port})"),
        (6, 302014, f"Teardown TCP connection {cid} for outside:{ext}/{sp} to inside:{inside}/{port} duration 0:{r.randrange(0, 59):02d}:{r.randrange(0, 59):02d} bytes {int(r.lognormvariate(9, 1.5))} TCP FINs"),
        (4, 106100, f"access-list outside_access_in denied tcp outside/{ext}({sp}) -> inside/{inside}({port}) hit-cnt {r.randrange(1, 30)} first hit [0x5a1b2c3d, 0x0]"),
        (6, 305011, f"Built dynamic TCP translation from inside:{inside}/{sp} to outside:203.0.113.10/{sp}"),
        (3, 113005, f"AAA user authentication Rejected : reason = Invalid password : server = 10.20.0.50 : user = admin : user IP = {ext}"),
        (6, 302015, f"Built outbound UDP connection {cid} for outside:8.8.8.8/53 (8.8.8.8/53) to inside:{inside}/{sp} (203.0.113.10/{sp})"),
        (6, 302016, f"Teardown UDP connection {cid} for outside:8.8.8.8/53 to inside:{inside}/{sp} duration 0:00:{r.randrange(1, 59):02d} bytes {r.randrange(80, 900)}"),
        (6, 106015, f"Deny TCP (no connection) from {ext}/{sp} to {inside}/{port} flags RST on interface outside"),
        (4, 710003, f"TCP access denied by ACL from {ext}/{sp} to outside:{inside}/{port}"),
    ], weights=[26, 24, 12, 14, 3, 6, 6, 6, 3])[0]
    pri = 20 * 8 + tpl[0]  # facility local4 (20), severity
    return {"message": f"<{pri}>{_asa_ts(c.ts)} {host} : %ASA-{tpl[0]}-{tpl[1]}: {tpl[2]}", "tags": ["cisco-asa", "forwarded"],
            "input": {"type": "udp"}, "log": {"source": {"address": "10.20.0.23:50033"}}}


MAC_PREFIX = ["AA:BB:CC", "3C:A3:1A", "F0:9F:C2", "00:18:0A"]
SSIDS = ["FreeWifi", "Starbucks-Guest", "iPhone-Hotspot", "CorpGuest", "NETGEAR55", "xfinitywifi", "Corp-WiFi", "Corp-WiFi-5G"]


def _mac(r) -> str:
    return r.choice(MAC_PREFIX) + ":" + ":".join(f"{r.randrange(256):02X}" for _ in range(3))


def _meraki(c: Ctx) -> dict:
    r = c.rng
    sub = r.choices(["rogue_ssid_detected", "ssid_spoofing_detected"], weights=[0.65, 0.35])[0]
    ssid = r.choice(SSIDS[:6]) if sub == "rogue_ssid_detected" else r.choice(SSIDS[6:])
    ap = f"meraki-mr-{r.randrange(1, 5):02d}"
    m = _mac(r)
    ns = f"{int(c.ts.timestamp())}.{r.randrange(10**8, 10**9)}"
    line = (f"<134>1 {ns} {ap} airmarshal_events type={sub} ssid='{ssid}' bssid='{m}' src='{m}' dst='FF:FF:FF:FF:FF:FF' wired_mac='{_mac(r)}' "
            f"vlan_id='0' channel='{r.choice([1, 6, 11, 36, 44])}' rssi='{r.randrange(-90, -40)}' fc_type='0' fc_subtype='8' vap='{r.randrange(0, 4)}'")
    return {"message": line, "tags": ["cisco-meraki", "forwarded"], "input": {"type": "udp"}, "log": {"source": {"address": "10.20.1.29:45073"}}}


registry.register(rest.GROUP, Generator(ASA, _asa, rate_per_min=0.8), Generator(MER, _meraki, rate_per_min=0.25))
