"""Slack Audit Logs API events (package `slack`, raw events through the package pipeline).

A fictional workspace "Corp Engineering" (team T0CORP01): logins, file shares and downloads, channel creation and joins, app installs,
role changes and a few anomaly events (new device or location).
"""
from __future__ import annotations

import uuid

from .. import profile, registry
from ..registry import Ctx, Generator
from .devtools import S, J, agent_block

STREAM = S["slack/audit"]
TEAM = "T0CORP01"
USERS = [(f"U{profile_n:08X}", n, f"{n.replace(' ', '.').lower()}@corp.example.org") for profile_n, n in
         enumerate(["Alice Martin", "Bob Chen", "Carol Novak", "Dave Okafor", "Erin Ito", "Frank Silva", "Grace Haddad", "Heidi Kowalski", "Ivan Reyes",
                    "Judy Tan", "Ken Lee", "Lena Park", "Mallory Wu", "Nina Cho", "Oscar Diaz", "Peggy Ng", "Quinn Sato", "Rosa Khan"], start=0x1A2B0000)]
CHANNELS = [("C0GENERAL1", "general"), ("C0ENG0001", "eng-platform"), ("C0ENG0002", "eng-backend"), ("C0INCIDENT", "incidents"), ("C0RANDOM01", "random"),
            ("C0SECURITY", "security-alerts"), ("C0ONCALL01", "oncall"), ("C0RELEASES", "releases")]
APPS = [("A0GITHUB01", "GitHub"), ("A0PAGERDUT", "PagerDuty"), ("A0JIRA0001", "Jira Cloud"), ("A0GDRIVE01", "Google Drive"), ("A0ZOOM0001", "Zoom"), ("A0DATADOG1", "Datadog")]
FILES = [("F0A1", "architecture-v3.pdf", "pdf"), ("F0A2", "q4-roadmap.xlsx", "xlsx"), ("F0A3", "incident-1042-timeline.png", "png"), ("F0A4", "design-review.fig", "fig"),
         ("F0A5", "onboarding-checklist.docx", "docx"), ("F0A6", "load-test-results.csv", "csv")]
UAS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
       "Slack/4.40.128 (Macintosh; Intel Mac OS X 14.6.1) Electron/32.2.5", "Slack/4.40.128 (Windows 10.0.22631) Electron/32.2.5",
       "Slack iOS 24.10.30 (iPhone15,3; iOS 18.0.1)", "Slack Android 24.10.30 (Pixel 8; Android 15)"]
IPS = ["81.2.69.142", "81.2.69.144", "81.2.69.160", "216.160.83.56", "89.160.20.112", "89.160.20.128", "2.125.160.216", "67.43.156.0", "175.16.199.0",
       "202.196.224.0", "128.101.101.101", "89.160.20.156"]
LOCATIONS = ["Singapore, SG", "London, GB", "Amsterdam, NL", "San Francisco, US", "Sydney, AU", "Berlin, DE"]
ACTIONS = [("user_login", 0.32), ("user_logout", 0.12), ("file_downloaded", 0.12), ("file_uploaded", 0.08), ("file_shared", 0.05), ("user_channel_join", 0.07),
           ("user_channel_leave", 0.03), ("channel_created", 0.02), ("app_installed", 0.015), ("app_uninstalled", 0.005), ("role_change_to_admin", 0.004),
           ("role_change_to_owner", 0.001), ("pref.two_factor_auth_changed", 0.01), ("user_login_failed", 0.06), ("anomaly", 0.012), ("channel_archive", 0.006),
           ("workflow_created", 0.01), ("user_created", 0.005), ("user_deactivated", 0.004), ("message_deleted", 0.015)]


def _event(c: Ctx) -> dict:
    r = c.rng
    action = profile.pick(r, ACTIONS)
    uid, uname, email = r.choice(USERS)
    actor = {"type": "user", "user": {"id": uid, "name": uname, "email": email, "team": TEAM}}
    loc = {"id": TEAM, "name": "Corp Engineering", "domain": "corp-eng", "type": "workspace"}
    ctx = {"ip_address": r.choice(IPS), "ua": r.choice(UAS), "location": loc, "session_id": r.getrandbits(40)}
    details: dict = {}
    entity: dict
    if action in ("user_login", "user_login_failed", "user_logout", "pref.two_factor_auth_changed", "user_deactivated", "user_created", "role_change_to_admin", "role_change_to_owner"):
        tu = r.choice(USERS) if action in ("user_deactivated", "user_created", "role_change_to_admin", "role_change_to_owner") else (uid, uname, email)
        entity = {"type": "user", "user": {"id": tu[0], "name": tu[1], "email": tu[2], "team": TEAM}}
        if action == "user_login_failed":
            details = {"reason": r.choice(["invalid_password", "sso_failure", "2fa_failed"])}
    elif action in ("file_downloaded", "file_uploaded", "file_shared"):
        fid, fname, ftype = r.choice(FILES)
        entity = {"type": "file", "file": {"id": fid, "name": fname, "filetype": ftype, "title": fname}}
        details = {"md5_hash": f"{r.getrandbits(128):032x}"} if action != "file_shared" else {"shared_to": r.choice(CHANNELS)[1]}
    elif action in ("user_channel_join", "user_channel_leave", "channel_created", "channel_archive", "message_deleted"):
        cid, cname = r.choice(CHANNELS)
        entity = {"type": "channel", "channel": {"id": cid, "name": cname, "privacy": r.choice(["public", "public", "private"]), "is_shared": False}}
        if action == "message_deleted":
            details = {"deleted_by": "author"}
    elif action in ("app_installed", "app_uninstalled"):
        aid, aname = r.choice(APPS)
        entity = {"type": "app", "app": {"id": aid, "name": aname, "is_distributed": False, "is_directory_approved": True, "scopes": ["chat:write", "channels:read"]}}
    elif action == "workflow_created":
        entity = {"type": "workflow", "workflow": {"id": f"Wf{r.randrange(10_000, 99_999)}", "name": r.choice(["Standup reminder", "PTO request", "Incident intake"])}}
    else:  # anomaly: new location or device for a user
        entity = {"type": "user", "user": {"id": uid, "name": uname, "email": email, "team": TEAM}}
        details = {"action_timestamp": int(c.ts.timestamp() * 1_000_000), "location": r.choice(LOCATIONS), "previous_ip_address": r.choice(IPS), "previous_ua": r.choice(UAS),
                   "reason": r.sample(["asn", "ip_address", "session_fingerprint", "user_agent"], k=r.randrange(1, 3))}
    ev = {"id": str(uuid.UUID(int=r.getrandbits(128), version=4)), "date_create": int(c.ts.timestamp()), "action": action, "actor": actor, "entity": entity, "context": ctx}
    if details:
        ev["details"] = details
    return {"message": J(ev), "input": {"type": "httpjson"}, "agent": agent_block("slack-audit-01", "filebeat"), "tags": ["forwarded", "slack-audit"]}


registry.register("devtools", Generator(STREAM, _event, rate_per_min=2.4))
