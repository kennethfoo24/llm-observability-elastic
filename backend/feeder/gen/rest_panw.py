"""Palo Alto Networks PAN-OS (panw.panos): RAW syslog CSV lines through the package pipeline `logs-panw.panos-5.5.0`.

One generator for the stream (type picked per event) because document ids and the state are per stream. The CSV column
order of every log type is the target_fields list of the package pipeline (`templates/panw/csv_fields.json`, extracted from
the installed pipeline); the generator names the columns it fills and every other column stays empty, so the line always
has the exact width the pipeline expects.
Types: TRAFFIC, THREAT, DECRYPTION, GLOBALPROTECT, SYSTEM, CONFIG, USERID, IPTAG, AUTHENTICATION, HIP-MATCH,
CORRELATION, START/END (tunnel inspection), GTP, SCTP.
"""
from __future__ import annotations

import functools
import json
from datetime import datetime, timedelta
from pathlib import Path

from .. import catalog, profile, registry
from ..registry import Ctx, Generator
from . import rest

S = rest.S["panw/panos"]
FIELDS: dict[str, list[str]] = json.loads((catalog.TEMPLATES / "panw" / "csv_fields.json").read_text())

FIREWALLS = [("palo-fw-prod", "001901000001"), ("palo-fw-dc", "007051000002")]
# type -> weight (traffic and threat dominate, the rest keeps every dashboard populated)
TYPES = [("TRAFFIC", 30), ("THREAT", 16), ("DECRYPTION", 8), ("GLOBALPROTECT", 6), ("SYSTEM", 4), ("CONFIG", 4), ("USERID", 5),
         ("IPTAG", 3), ("AUTHENTICATION", 4), ("HIP-MATCH", 3), ("CORRELATION", 2), ("TUNNEL", 4), ("GTP", 4), ("SCTP", 4)]
# application: (name, category, sub_category, technology, risk, characteristics, saas)
APPS = [
    ("ssl", "networking", "encrypted-tunnel", "browser-based", 4, "", "no"),
    ("web-browsing", "general-internet", "internet-utility", "browser-based", 4, "used-by-malware;has-known-vulnerability;pervasive-use", "no"),
    ("dns", "networking", "infrastructure", "network-protocol", 2, "used-by-malware;pervasive-use", "no"),
    ("ms-office365", "collaboration", "email", "client-server", 2, "excessive-bandwidth;pervasive-use", "yes"),
    ("slack-base", "collaboration", "instant-messaging", "client-server", 2, "pervasive-use", "yes"),
    ("ssh", "networking", "remote-access", "client-server", 3, "used-by-malware;pervasive-use", "no"),
    ("youtube-base", "media", "photo-video", "browser-based", 3, "excessive-bandwidth;pervasive-use", "no"),
    ("dropbox-base", "general-internet", "file-sharing", "client-server", 4, "data-leak;has-known-vulnerability", "yes"),
    ("bittorrent", "general-internet", "file-sharing", "peer-to-peer", 5, "excessive-bandwidth;evasive-behavior;used-by-malware", "no"),
    ("ms-rdp", "networking", "remote-access", "client-server", 4, "used-by-malware;has-known-vulnerability", "no"),
    ("smb", "business-systems", "storage-backup", "client-server", 3, "used-by-malware;has-known-vulnerability", "no"),
    ("github-base", "business-systems", "software-development", "browser-based", 2, "pervasive-use", "yes"),
    ("tor", "networking", "proxy", "client-server", 5, "evasive-behavior;used-by-malware;tunnel-other-application", "no"),
    ("ipsec-esp-udp", "networking", "encrypted-tunnel", "network-protocol", 1, "", "no"),
]
INTERNAL_USERS = [f"corp\\{n}" for n in ("alice.martin", "bob.chen", "carol.novak", "dave.okafor", "erin.ito", "frank.silva", "grace.haddad",
                                         "heidi.kowalski", "ivan.reyes", "judy.tan", "ken.martin", "lena.chen")]
EXTERNAL = ["81.2.69.142", "216.160.83.56", "89.160.20.112", "2.125.160.216", "67.43.156.0", "175.16.199.0", "202.196.224.0", "128.101.101.101",
            "89.160.20.156", "8.8.8.8", "1.1.1.1", "142.250.190.78", "151.101.1.69", "13.107.42.14", "52.94.76.10", "104.18.32.47"]
SNI = ["login.microsoftonline.com", "api.github.com", "www.youtube.com", "slack.com", "cdn.jsdelivr.net", "s3.amazonaws.com", "update.example-bank.com",
       "files.dropbox.com", "expired.badssl.com", "self-signed.badssl.com", "teams.microsoft.com", "unknown-cdn.example.net"]
THREATS = [("Microsoft Windows SMB Remote Code Execution Vulnerability(37590)", "vulnerability", "critical", "code-execution", "smb"),
           ("Apache Log4j Remote Code Execution Vulnerability(92001)", "vulnerability", "critical", "code-execution", "web-browsing"),
           ("HTTP Directory Traversal Vulnerability(30851)", "vulnerability", "high", "code-execution", "web-browsing"),
           ("SSH User Authentication Brute-force Attempt(40015)", "vulnerability", "high", "brute-force", "ssh"),
           ("Generic.Trojan.Zeus Command and Control Traffic(13600)", "spyware", "high", "command-and-control", "ssl"),
           ("Suspicious DNS Query(4000012)", "spyware", "medium", "dns", "dns"),
           ("WildFire Virus: Trojan.Win32.Agent(52100)", "virus", "medium", "malware", "web-browsing"),
           ("Phishing: shop-secure-login(0)", "url", "low", "phishing", "web-browsing"),
           ("Informational: Port Scan(8500)", "vulnerability", "informational", "info-leak", "ssl"),
           ("TCP Port Scan(8001)", "scan", "medium", "scan", "ssl")]
URLS = ["login.example-secure.com/verify", "cdn.suspicious-files.net/payload.exe", "update.example-bank.com/login", "files.mega-share.io/dl/9912",
        "shop.example.org/api/v1/cart", "mail.example-phish.ru/id=4491"]
GP_GATEWAYS = ["gp-gw-sin", "gp-gw-hkg", "gp-gw-syd"]


def _q(v) -> str:
    s = "" if v is None else str(v)
    return '"' + s.replace('"', '""') + '"' if ("," in s or '"' in s) else s


def row(kind: str, vals: dict) -> str:
    """CSV body of a log type: the pipeline columns in order, unnamed columns empty."""
    return ",".join(_q(vals.get(f, "")) for f in FIELDS[kind])


def _ts(ts: datetime) -> str:
    return ts.strftime("%Y/%m/%d %H:%M:%S")


def _hires(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}+00:00"


@functools.lru_cache(maxsize=None)
def _apps_by_name() -> dict:
    return {a[0]: a for a in APPS}


def _app_cols(app: tuple) -> dict:
    return {"panw.panos.application.sub_category": app[2], "panw.panos.application.category": app[1],
            "panw.panos.application.technology": app[3], "panw.panos.application.risk_level": str(app[4]),
            "panw.panos.application.characteristics": app[5], "panw.panos.application.container": "",
            "panw.panos.application.tunneled": "no", "panw.panos.application.is_saas": app[6],
            "panw.panos.application.is_sanctioned": "no" if app[6] == "yes" and app[4] > 3 else "yes"}


def _common(c: Ctx, fw: tuple[str, str]) -> dict:
    return {"panw.panos.virtual_sys": "vsys1", "panw.panos.vsys_name": "vsys1", "panw.panos.vsys_id": "1", "panw.panos.device_name": fw[0],
            "panw.panos.sequence_number": str(7_000_000 + int(c.ts.timestamp()) % 9_000_000 + c.i), "panw.panos.action_flags": "0x8000000000000000",
            "panw.panos.device_group_hierarchy1": "0", "panw.panos.device_group_hierarchy2": "0",
            "panw.panos.device_group_hierarchy3": "0", "panw.panos.device_group_hierarchy4": "0",
            "_temp_.high_res_timestamp": _hires(c.ts)}


def _pair(r) -> tuple[str, str, str, str]:
    """(src ip, dst ip, srcloc, dstloc): mostly internal -> external, some internal -> internal and inbound."""
    inside = f"10.10.{r.randrange(1, 40)}.{r.randrange(2, 250)}"
    server = f"10.20.{r.randrange(1, 12)}.{r.randrange(2, 250)}"
    ext = r.choice(EXTERNAL)
    k = r.random()
    if k < 0.62:
        return inside, ext, "10.0.0.0-10.255.255.255", ext
    if k < 0.82:
        return inside, server, "10.0.0.0-10.255.255.255", "10.0.0.0-10.255.255.255"
    return ext, server, ext, "10.0.0.0-10.255.255.255"


def _flow(c: Ctx, fw: tuple[str, str], app: tuple, action: str = "allow") -> dict:
    r = c.rng
    src, dst, sloc, dloc = _pair(r)
    proto = "udp" if app[0] in ("dns", "ipsec-esp-udp") else "tcp"
    dport = {"ssl": 443, "web-browsing": 80, "dns": 53, "ssh": 22, "ms-rdp": 3389, "smb": 445, "ipsec-esp-udp": 4500}.get(app[0], 443)
    snat = "203.0.113.10" if dloc != "10.0.0.0-10.255.255.255" else src
    v = _common(c, fw)
    v.update({"panw.panos.source.ip": src, "panw.panos.destination.ip": dst, "panw.panos.source.nat.ip": snat, "panw.panos.destination.nat.ip": dst,
              "panw.panos.ruleset": "allow-egress" if action == "allow" else "block-risky", "_temp_.srcuser": r.choice(INTERNAL_USERS) if src.startswith("10.10") else "",
              "panw.panos.network.application": app[0], "panw.panos.source.zone": "inside" if src.startswith("10.") else "outside",
              "panw.panos.destination.zone": "outside" if not dst.startswith("10.") else "inside", "panw.panos.inbound_interface": "ethernet1/1",
              "panw.panos.outbound_interface": "ethernet1/2", "panw.panos.log_profile": "default-log-profile", "panw.panos.flow_id": str(r.randrange(10000, 900000)),
              "panw.panos.repeat_count": "1", "panw.panos.source.port": str(r.randrange(20000, 60000)), "panw.panos.destination.port": str(dport),
              "panw.panos.source.nat.port": str(r.randrange(20000, 60000)), "panw.panos.destination.nat.port": str(dport),
              "_temp_.labels": "0x0", "panw.panos.protocol": proto, "panw.panos.action": action, "_temp_.srcloc": sloc, "_temp_.dstloc": dloc,
              "panw.panos.rule_uuid": "9e1f5d8c-4b0a-4a1c-9d57-0c2f9a1b7e11"})
    v.update(_app_cols(app))
    return v


def _traffic(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    app = r.choices(APPS, weights=[30, 18, 12, 8, 5, 3, 5, 3, 2, 3, 4, 3, 1, 3])[0]
    deny = r.random() < 0.08 or app[0] in ("bittorrent", "tor") and r.random() < 0.8
    v = _flow(c, fw, app, "deny" if deny else "allow")
    sent, recv = int(r.lognormvariate(8.5, 1.4)), int(r.lognormvariate(9.5, 1.5))
    dur = 0 if deny else int(r.lognormvariate(2.5, 1.2))
    start = c.ts - timedelta(seconds=dur)
    v.update({"_temp_.future_use1": _ts(c.ts), "panw.panos.network.bytes": str(sent + recv), "panw.panos.bytes_sent": str(sent), "panw.panos.bytes_received": str(recv),
              "panw.panos.network.packets": str(max(2, (sent + recv) // 900)), "panw.panos.start_time": _ts(start), "panw.panos.elapsed_time": str(dur),
              "panw.panos.url.category": r.choice(["business-and-economy", "computer-and-internet-info", "social-networking", "streaming-media", "any"]),
              "panw.panos.packets_sent": str(max(1, sent // 900)), "panw.panos.packets_received": str(max(1, recv // 900)),
              "panw.panos.endreason": "policy-deny" if deny else r.choice(["tcp-fin", "tcp-fin", "aged-out", "tcp-rst-from-client", "tcp-rst-from-server"]),
              "panw.panos.action_source": "from-policy", "panw.panos.tunnel_type": "N/A", "panw.panos.is_offloaded": "no"})
    return "TRAFFIC", "drop" if deny else "end", row("traffic", v)


def _threat(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    name, sub, sev, cat, appn = r.choice(THREATS)
    app = _apps_by_name()[appn]
    v = _flow(c, fw, app, r.choice(["alert", "alert", "reset-both", "drop", "block-url"]))
    ext = r.choice(EXTERNAL)
    v["panw.panos.source.ip"], v["panw.panos.destination.ip"] = ext, f"10.20.{r.randrange(1, 12)}.{r.randrange(2, 250)}"
    v["panw.panos.source.nat.ip"], v["panw.panos.destination.nat.ip"] = ext, v["panw.panos.destination.ip"]
    v["_temp_.srcloc"], v["_temp_.dstloc"] = ext, "10.0.0.0-10.255.255.255"
    v.update({"_temp_.logged_time": _ts(c.ts), "panw.panos.threat.name": name, "panw.panos.misc": r.choice(URLS) if sub in ("url", "virus") else "",
              "panw.panos.url.category": "malware" if sub == "virus" else "computer-and-internet-info", "panw.panos.severity": sev,
              "_temp_.direction": "client-to-server", "_temp_.user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
              "panw.panos.http_method": "get", "panw.panos.threat_category": cat, "panw.panos.content_version": "AppThreat-8892-9421",
              "panw.panos.http_content_type": "text/html", "panw.panos.url_idx": "1", "panw.panos.tunnel_type": "N/A"})
    return "THREAT", sub, row("threat", v)


def _decryption(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    app = r.choices(APPS[:8], weights=[40, 10, 3, 10, 6, 4, 6, 4])[0]
    v = _flow(c, fw, app, r.choice(["decrypt", "decrypt", "no-decrypt"]))
    fail = r.random() < 0.18
    sni = r.choice(SNI)
    v.update({"_temp_.logged_time": _ts(c.ts), "_temp_.tls": r.choice(["TLS1.2", "TLS1.2", "TLS1.3"]), "panw.panos.tls.key_exchange_algorithm": r.choice(["ECDHE", "ECDHE", "RSA", "DHE"]),
              "panw.panos.tls.encryption": r.choice(["AES_256_GCM", "AES_128_GCM", "CHACHA20_POLY1305", "AES_256_CBC"]),
              "panw.panos.tls.auth": r.choice(["SHA384", "SHA256", "SHA1"]), "panw.panos.policy.name": "decrypt-outbound",
              "panw.panos.elliptic_curve": "secp256r1", "panw.panos.tls.error_type": "ssl-handshake-failure" if fail else "",
              "panw.panos.root_certificate_status": "trusted", "panw.panos.chain_status": "Incomplete" if fail else r.choice(["Trusted", "Trusted", "Untrusted"]),
              "panw.panos.proxy_type": r.choice(["Forward", "Forward", "Inbound"]), "panw.panos.certificate.serial_number": "0" + uid_hex(r, 16),
              "_temp_.hash": "sha256", "panw.panos.certificate.not_before": "2026/01/05 00:00:00", "panw.panos.certificate.not_after": "2027/01/05 23:59:59",
              "panw.panos.certificate.version": "3", "panw.panos.certificate.size": "2048", "panw.panos.subject_common_name.value": sni,
              "panw.panos.issuer_common_name.value": "DigiCert Global G2 TLS RSA SHA256 2020 CA1", "panw.panos.root_common_name.value": "DigiCert Global Root G2",
              "panw.panos.server_name_indication.value": sni, "panw.panos.error_message": r.choice(["Certificate expired", "Unsupported cipher suite", "Untrusted issuer", "Client cert required"]) if fail else "",
              "panw.panos.tunnel_type": "N/A"})
    return "DECRYPTION", "", row("decryption", v)


def uid_hex(r, n: int) -> str:
    return "".join(r.choice("0123456789ABCDEF") for _ in range(n))


def _globalprotect(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    user = r.choice(INTERNAL_USERS)
    os_ = r.choice([("Windows", "Microsoft Windows 11 Enterprise , 64-bit"), ("macOS", "Apple Mac OS X 14.5.0"), ("iOS", "Apple iOS 17.5"), ("Linux", "Ubuntu 22.04"),
                    ("Android", "Google Android 14")])
    v = _common(c, fw)
    v.update({"panw.panos.event.id": r.choice(["gateway-auth", "gateway-auth", "gateway-config-release", "portal-auth", "gateway-agent-msg", "gateway-getconfig"]),
              "panw.panos.stage": r.choice(["login", "login", "tunnel", "connected"]), "panw.panos.auth_method": r.choice(["SAML", "LDAP", "Certificate", "Local"]),
              "panw.panos.tunnel_type": "IPSec", "_temp_.srcuser": user, "_temp_.srcloc": r.choice(["Singapore", "Malaysia", "Australia", "Japan"]),
              "panw.panos.machine.name": "LAPTOP-" + uid_hex(r, 5), "panw.panos.public.ip": r.choice(EXTERNAL), "panw.panos.private.ip": f"10.100.{r.randrange(1, 30)}.{r.randrange(2, 250)}",
              "panw.panos.host.id": uid_hex(r, 12).lower(), "panw.panos.serial_number": "C02" + uid_hex(r, 8), "panw.panos.client_ver": r.choice(["6.2.4-c11", "6.3.1-c91", "6.1.7-c21"]),
              "panw.panos.client.os": os_[1], "panw.panos.client.os_version": os_[1], "panw.panos.repeat_count": "1",
              "panw.panos.event.reason": "", "panw.panos.error_message": "", "panw.panos.description": "GlobalProtect gateway user authentication succeeded.",
              "panw.panos.event.status": r.choice(["success", "success", "success", "failure"]), "panw.panos.location": r.choice(["Singapore", "Hong Kong", "Sydney"]),
              "panw.panos.login_duration": str(r.randrange(1, 40)), "panw.panos.connect_method": r.choice(["On-demand", "Pre-logon", "User-logon"]), "panw.panos.error_code": "0",
              "panw.panos.portal": "gp-portal.corp.example.org", "panw.panos.selection_type": r.choice(["Automatic", "Manual", "Preferred"]), "panw.panos.response_time": str(r.randrange(8, 120)),
              "panw.panos.priority": "1", "panw.panos.attempted_gateways": "gp-gw-sin", "panw.panos.gateway": r.choice(GP_GATEWAYS)})
    return "GLOBALPROTECT", "", row("globalprotect", v)


def _system(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    ev = r.choice([("general", "general", "informational", "Pushed content update to the dataplane"), ("auth", "auth", "informational", "User admin logged in via Web from 10.10.5.20"),
                   ("globalprotect", "globalprotect", "informational", "GlobalProtect gateway client configuration generated"), ("dhcp", "dhcp", "low", "DHCP lease renewed"),
                   ("ha", "ha", "medium", "HA1 link is up"), ("vpn", "vpn", "high", "IKE phase-2 negotiation failed"), ("general", "general", "critical", "Disk usage on / reached 90 percent")])
    v = _common(c, fw)
    v.update({"panw.panos.event.id": ev[0], "panw.panos.object.id": "", "panw.panos.module": ev[1], "panw.panos.severity": ev[2], "panw.panos.description": ev[3]})
    return "SYSTEM", ev[0], row("system", v)


def _config(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    cmd = r.choice(["edit", "set", "commit", "delete", "move", "rename"])
    v = _common(c, fw)
    v.update({"panw.panos.host.ip": f"10.10.5.{r.randrange(10, 30)}", "panw.panos.cmd": cmd, "panw.panos.admin": r.choice(["admin", "netops", "secops"]),
              "panw.panos.client_type": r.choice(["Web", "CLI", "Panorama"]), "panw.panos.result": r.choice(["Succeeded", "Succeeded", "Succeeded", "Failed", "Unauthorized"]),
              "panw.panos.path": "/config/devices/entry[@name='localhost.localdomain']/vsys/entry[@name='vsys1']/rulebase/security/rules/entry[@name='allow-egress']",
              "panw.panos.before_change_detail": "", "panw.panos.after_change_detail": "", "panw.panos.device_group_id": "0"})
    return "CONFIG", "0", row("config", v)


def _userid(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    v = _common(c, fw)
    v.update({"panw.panos.source.ip": f"10.10.{r.randrange(1, 40)}.{r.randrange(2, 250)}", "_temp_.srcuser": r.choice(INTERNAL_USERS),
              "panw.panos.datasourcename": r.choice(["ad-dc-01", "ad-dc-02", "captive-portal", "gp-gateway"]), "panw.panos.event.id": "login", "panw.panos.repeat_count": "1",
              "panw.panos.timeout": "2700", "panw.panos.source.port": "0", "panw.panos.destination.port": "0",
              "panw.panos.datasource": r.choice(["WinRM-Agent", "Syslog", "XML API", "User-ID Agent", "GlobalProtect"]),
              "panw.panos.datasourcetype": r.choice(["agent", "agent", "xml-api", "syslog", "globalprotect"]), "panw.panos.factortype": "", "panw.panos.factorno": "0",
              "panw.panos.ugflags": "0x0", "panw.panos.user_by_source": ""})
    return "USERID", "login", row("userid", v)


def _iptag(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    v = _common(c, fw)
    v.update({"panw.panos.source.ip": f"10.20.{r.randrange(1, 12)}.{r.randrange(2, 250)}", "panw.panos.tag.name": r.choice(["quarantine", "web-servers", "db-servers", "pci-scope", "vip-users"]),
              "panw.panos.event.id": r.choice(["register", "unregister"]), "panw.panos.repeat_count": "1", "panw.panos.timeout": "0",
              "panw.panos.datasourcename": r.choice(["vmware-vcenter", "aws-vm-monitor", "xml-api-automation", "cortex-xsoar"]),
              "panw.panos.datasource_type": r.choice(["unknown", "xml-api", "vm-monitor"]), "panw.panos.datasource_subtype": r.choice(["unknown", "VMware ESXi", "AWS VPC", "Azure"])})
    return "IPTAG", "", row("ip_tag", v)


def _auth(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    v = _common(c, fw)
    v.update({"panw.panos.source.ip": f"10.10.{r.randrange(1, 40)}.{r.randrange(2, 250)}", "_temp_.user": r.choice(INTERNAL_USERS), "panw.panos.normalize_user": r.choice(INTERNAL_USERS),
              "panw.panos.object.id": "captive-portal-auth", "panw.panos.authentication.policy": r.choice(["cp-sso-policy", "mfa-vpn-policy", "kerberos-policy"]),
              "panw.panos.repeat_count": "1", "panw.panos.authentication.id": str(r.randrange(100000, 999999)), "panw.panos.vendor": "Okta", "panw.panos.log_profile": "default-log-profile",
              "panw.panos.server_profile": "okta-saml", "panw.panos.description": "Authentication completed", "panw.panos.client_type": r.choice(["Browser", "GlobalProtect", "Mobile"]),
              "panw.panos.event.result": r.choice(["success", "success", "success", "failure", "timeout"]), "panw.panos.factorno": "1",
              "panw.panos.authentication.protocol": r.choice(["SAML", "RADIUS", "LDAP", "Kerberos"]), "panw.panos.rule_uuid": "9e1f5d8c-4b0a-4a1c-9d57-0c2f9a1b7e22",
              "panw.panos.flow_id": str(r.randrange(10000, 900000))})
    return "AUTHENTICATION", "", row("authentication", v)


def _hip(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    os_ = r.choice(["Microsoft Windows 11 Enterprise , 64-bit", "Apple Mac OS X 14.5.0", "Ubuntu 22.04", "Microsoft Windows 10 Pro , 64-bit"])
    v = _common(c, fw)
    v.update({"_temp_.srcuser": r.choice(INTERNAL_USERS), "panw.panos.machine.name": "LAPTOP-" + uid_hex(r, 5), "panw.panos.machine.os": os_,
              "panw.panos.source.ip": f"10.100.{r.randrange(1, 30)}.{r.randrange(2, 250)}", "panw.panos.matchname": r.choice(["Disk-Encrypted", "AV-Updated", "Firewall-On", "Patch-Current", "Jailbroken-Check"]),
              "panw.panos.repeat_count": "1", "panw.panos.matchtype": r.choice(["object", "profile"]), "panw.panos.host.id": uid_hex(r, 12).lower(),
              "panw.panos.serial_number": "C02" + uid_hex(r, 8), "panw.panos.machine.mac_address": "00:1B:44:" + ":".join(uid_hex(r, 2) for _ in range(3))})
    return "HIP-MATCH", "0", row("hipmatch", v)


def _correlation(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    o = r.choice([("Compromised Host", "compromised-host", "high"), ("Beacon Detected", "beacon-detected", "medium"), ("Brute Force Success", "brute-force", "critical"),
                  ("Suspicious Download Followed By Callback", "malware-chain", "low")])
    v = _common(c, fw)
    v.update({"panw.panos.source.ip": f"10.10.{r.randrange(1, 40)}.{r.randrange(2, 250)}", "_temp_.srcuser": r.choice(INTERNAL_USERS), "panw.panos.category": "compromised-host",
              "panw.panos.severity": o[2], "panw.panos.object.name": o[0], "panw.panos.object.id": "6" + str(r.randrange(100, 999)),
              "panw.panos.evidence": "Host visited a known malware URL 8 times and 4 DNS queries to a C2 domain"})
    return "CORRELATION", "", row("correlated_event", v)


def _tunnel(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    app = r.choice(APPS)
    v = _flow(c, fw, app, r.choice(["allow", "allow", "deny"]))
    sent, recv = int(r.lognormvariate(9, 1)), int(r.lognormvariate(9, 1))
    v.update({"panw.panos.severity": r.choice(["informational", "low", "medium", "high"]), "panw.panos.tunnel_type": r.choice(["GRE", "IPSec", "VXLAN", "GTP-U"]),
              "panw.panos.network.bytes": str(sent + recv), "panw.panos.bytes_sent": str(sent), "panw.panos.bytes_received": str(recv), "panw.panos.network.packets": str((sent + recv) // 900 + 2),
              "panw.panos.packets_sent": str(sent // 900 + 1), "panw.panos.packets_received": str(recv // 900 + 1), "panw.panos.max_encapsulation": "0", "panw.panos.unknown_protocol": "0",
              "panw.panos.strict_check": "0", "panw.panos.tunnel_fragment": "0", "panw.panos.sessions.created": "1", "panw.panos.sessions.closed": "1",
              "panw.panos.endreason": r.choice(["tcp-fin", "aged-out", "policy-deny"]), "panw.panos.action_source": r.choice(["from-policy", "from-application"]),
              "panw.panos.start_time": _ts(c.ts - timedelta(seconds=30)), "panw.panos.elapsed_time": "30", "panw.panos.tunnel_inspection_rule": "inspect-gre"})
    typ = r.choice(["START", "END"])
    return typ, "", row("tunnel_inspection", v)


def _gtp(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    app = r.choice([("gtpv1-c", "networking", "infrastructure", "network-protocol", 2, "", "no"), ("gtpv2-c", "networking", "infrastructure", "network-protocol", 2, "", "no"),
                    ("gtp-u", "networking", "infrastructure", "network-protocol", 1, "", "no")])
    v = _flow(c, fw, app, r.choice(["allow", "allow", "drop"]))
    v.update({"panw.panos.event_type": r.choice(["tunnel-end", "tunnel-start", "message-drop"]), "panw.panos.msisdn": "6591" + str(r.randrange(100000, 999999)), "panw.panos.access_point.name": "internet.corp",
              "panw.panos.radio_access_technology_type": r.choice(["EUTRAN", "UTRAN", "WLAN", "GERAN"]), "panw.panos.message_type": r.choice(["create-session-request", "delete-session-request", "echo-request", "modify-bearer-request"]),
              "panw.panos.end_ip_address": f"10.200.{r.randrange(1, 30)}.{r.randrange(2, 250)}", "panw.panos.tunnel_endpoint.identifier1": str(r.randrange(1000, 9999)),
              "panw.panos.tunnel_endpoint.identifier2": str(r.randrange(1000, 9999)), "panw.panos.interface": "S5/S8", "panw.panos.cause_code": "16", "panw.panos.severity": r.choice(["informational", "low", "medium", "high"]),
              "panw.panos.mcc": "525", "panw.panos.mnc": "01", "panw.panos.area_code": "4021", "panw.panos.cell.id": str(r.randrange(1000, 9999)), "panw.panos.event_code": "1",
              "_temp_.srcloc": "10.0.0.0-10.255.255.255", "_temp_.dstloc": "10.0.0.0-10.255.255.255", "panw.panos.imsi": "5250100" + str(r.randrange(10**7, 10**8)),
              "panw.panos.imei": "35" + str(r.randrange(10**12, 10**13)), "panw.panos.start_time": _ts(c.ts - timedelta(seconds=20)), "panw.panos.elapsed_time": "20",
              "panw.panos.tunnel_inspection_rule": "inspect-gtp", "panw.panos.remote_user.ip": "", "panw.panos.remote_user.id": "", "panw.panos.pcap_id": "0", "panw.panos.nsdsai_sst": "", "panw.panos.nsdsai_sd": ""})
    return "GTP", "", row("gtp", v)


def _sctp(c: Ctx, fw) -> tuple[str, str, str]:
    r = c.rng
    v = _flow(c, fw, ("sctp", "networking", "infrastructure", "network-protocol", 2, "", "no"), r.choice(["allow", "allow", "drop"]))
    v.update({"panw.panos.severity": r.choice(["informational", "low", "medium", "high"]), "panw.panos.sctp.assoc_id": str(r.randrange(1, 9999)), "panw.panos.payload_protocol_id": "3",
              "panw.panos.sctp.chunk_type": r.choice(["INIT", "ABORT", "SHUTDOWN", "DATA"]), "panw.panos.sctp.verification.tag_1": str(r.randrange(10**6, 10**9)),
              "panw.panos.sctp.verification.tag_2": str(r.randrange(10**6, 10**9)), "panw.panos.sctp.cause_code": "0", "panw.panos.diameter_app_id": "0", "panw.panos.diameter_cmd_code": "0",
              "panw.panos.diameter_avp_code": "0", "panw.panos.sctp.stream_id": "0",
              "panw.panos.sctp.assoc_end_reason": r.choice(["shutdown-complete", "abort-received", "timeout", "policy-deny"]),
              "panw.panos.op_code": r.choice(["update-location", "cancel-location", "send-routing-info", "insert-subscriber-data"]), "panw.panos.sccp.calling_ssn": "6",
              "panw.panos.sccp.calling_gt": "6591" + str(r.randrange(10000, 99999)), "panw.panos.sctp.filter": r.choice(["map-filter-1", "diameter-filter-2", "sctp-default"]),
              "panw.panos.sctp.chunks": "12", "panw.panos.sctp.chunks_sent": "7", "panw.panos.sctp.chunks_received": "5", "panw.panos.network.packets": "12",
              "panw.panos.packets_sent": "7", "panw.panos.packets_received": "5"})
    return "SCTP", "", row("sctp", v)


BUILD = {"TRAFFIC": _traffic, "THREAT": _threat, "DECRYPTION": _decryption, "GLOBALPROTECT": _globalprotect, "SYSTEM": _system, "CONFIG": _config,
         "USERID": _userid, "IPTAG": _iptag, "AUTHENTICATION": _auth, "HIP-MATCH": _hip, "CORRELATION": _correlation, "TUNNEL": _tunnel, "GTP": _gtp,
         "SCTP": _sctp}


def _panos(c: Ctx) -> dict:
    r = c.rng
    fw = FIREWALLS[r.randrange(len(FIREWALLS))] if r.random() < 0.35 else FIREWALLS[0]
    kind = profile.pick(r, [(k, w) for k, w in TYPES])
    typ, sub, body = BUILD[kind](c, fw)
    line = f"1,{_ts(c.ts)},{fw[1]},{typ},{sub},2562,{_ts(c.ts)},{body}"
    return {"message": line, "tags": ["panw-panos", "forwarded"],
            "log": {"source": {"address": "10.20.0.25:514"}, "syslog": {"hostname": fw[0]}}, "input": {"type": "udp"},
            "observer": {"hostname": fw[0], "serial_number": fw[1]}, "agent": rest.agent_block("elastic-agent-synthetic", "filebeat")}


registry.register(rest.GROUP, Generator(S, _panos, rate_per_min=1.6))
