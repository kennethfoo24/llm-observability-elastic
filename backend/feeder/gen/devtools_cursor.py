"""Cursor team audit log (package `cursor`, raw events through the package pipeline).

A fictional 22 person engineering team on Cursor Business: logins and logouts dominate, with API key, MCP server, rule and command
changes, privacy mode and spend limit changes, and the occasional admin action (add or remove a user, role change).
"""
from __future__ import annotations

import uuid

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra
from .devtools import S, J, agent_block

STREAM = S["cursor/audit"]
TEAM_ID = 4821
TEAM = [f"{n}@corp.example.org" for n in ["alice.martin", "bob.chen", "carol.novak", "dave.okafor", "erin.ito", "frank.silva", "grace.haddad",
                                           "heidi.kowalski", "ivan.reyes", "judy.tan", "ken.lee", "lena.park", "mallory.wu", "nina.cho", "oscar.diaz",
                                           "peggy.ng", "quinn.sato", "rosa.khan", "sam.lim", "tina.roy", "uma.bose", "viktor.hale"]]
ADMINS = TEAM[:3]
IPS = ["81.2.69.142", "81.2.69.144", "81.2.69.160", "216.160.83.56", "89.160.20.112", "89.160.20.128", "2.125.160.216", "67.43.156.0", "175.16.199.0",
       "202.196.224.0", "128.101.101.101", "89.160.20.156"]
MCP = ["github-mcp", "linear-mcp", "postgres-mcp", "sentry-mcp", "filesystem-mcp", "figma-mcp"]
RULES = ["python-style", "no-secrets-in-code", "react-conventions", "sql-review", "terraform-guardrails"]
COMMANDS = ["review-pr", "write-tests", "explain-diff", "migrate-schema"]
SETTINGS = [("max_requests_per_user", "500", "800"), ("allowed_models", "default", "gpt-5,claude-sonnet"), ("pr_summaries", "off", "on"),
            ("sso_required", "false", "true"), ("privacy_mode_enforced", "false", "true")]
ACTIONS = [("login", 0.46), ("logout", 0.18), ("user_api_key", 0.06), ("mcp_server_config", 0.07), ("team_rule", 0.05), ("team_command", 0.03),
           ("privacy_mode", 0.03), ("team_settings", 0.03), ("user_spend_limit", 0.03), ("team_repo", 0.02), ("api_key", 0.01), ("team_hook", 0.01),
           ("update_user_role", 0.01), ("add_user", 0.005), ("remove_user", 0.005), ("invite_email_sent", 0.01), ("protected_git_scope_access_check", 0.02)]


def _event(c: Ctx) -> dict:
    r = c.rng
    action = profile.pick(r, ACTIONS)
    user = r.choice(ADMINS) if action in ("mcp_server_config", "team_rule", "team_command", "team_settings", "team_repo", "team_hook", "update_user_role",
                                          "add_user", "remove_user", "invite_email_sent", "user_spend_limit", "api_key") else r.choice(TEAM)
    ev: dict = {"event_id": str(uuid.UUID(int=r.getrandbits(128), version=4)), "timestamp": profile.iso(c.ts), "event_type": action, "ip_address": r.choice(IPS),
                "user_email": user, "team_id": TEAM_ID, "ghost_mode": False, "privacy_mode": r.random() < 0.7, "request_id": f"req_{r.getrandbits(40):010x}"}
    data: dict = {}
    if action == "login":
        ok = r.random() > 0.04
        data = {"login_type": r.choice(["LOGIN_TYPE_WEB", "LOGIN_TYPE_WEB", "LOGIN_TYPE_APP", "LOGIN_TYPE_SSO"]), "success": ok}
    elif action == "logout":
        data = {"source": r.choice(["web", "app"])}
    elif action in ("user_api_key", "api_key", "team_api_key"):
        data = {"action": r.choice(["created", "revoked", "rotated"]), "source": r.choice(["dashboard", "api"]), "method": "dashboard"}
    elif action == "mcp_server_config":
        data = {"action": r.choice(["added", "updated", "removed"]), "server_name": r.choice(MCP), "source": r.choice(["dashboard", "dashboard", "api"])}
    elif action == "team_rule":
        data = {"action": r.choice(["created", "updated", "deleted"]), "rule_id": f"rule_{r.randrange(100, 999)}", "rule_name": r.choice(RULES), "source": "dashboard"}
    elif action == "team_command":
        data = {"action": r.choice(["created", "updated"]), "command_id": f"cmd_{r.randrange(100, 999)}", "command_name": r.choice(COMMANDS), "source": "dashboard"}
    elif action == "privacy_mode":
        data = {"action": r.choice(["enabled", "disabled"]), "source": "dashboard"}
    elif action == "team_settings":
        name, old, new = r.choice(SETTINGS)
        data = {"setting_name": name, "old_value": old, "new_value": new, "source": "dashboard"}
    elif action == "user_spend_limit":
        data = {"target_user_email": r.choice(TEAM), "old_value": str(r.choice([20, 40, 60])), "new_value": str(r.choice([60, 80, 120])), "source": "dashboard"}
    elif action == "team_repo":
        data = {"action": r.choice(["added", "removed"]), "source": "dashboard"}
    elif action == "team_hook":
        data = {"action": "created", "hook_id": f"hook_{r.randrange(100, 999)}", "url": f"https://hooks.corp.example.org/cursor/{r.randrange(1, 9)}", "source": "dashboard"}
    elif action == "update_user_role":
        data = {"user_email": r.choice(TEAM), "old_role": "member", "new_role": r.choice(["admin", "member"]), "source": "dashboard"}
    elif action in ("add_user", "remove_user"):
        data = {"user_email": f"new.hire{r.randrange(1, 90)}@corp.example.org" if action == "add_user" else r.choice(TEAM), "role": "member", "source": r.choice(["dashboard", "scim"])}
    elif action == "invite_email_sent":
        data = {"recipient_email": f"candidate{r.randrange(1, 60)}@example.net", "source": "dashboard"}
    elif action == "protected_git_scope_access_check":
        data = {"result": r.choice(["allowed", "allowed", "allowed", "blocked"]), "source": "app"}
    ev["event_data"] = data
    return {"message": J(ev), "input": {"type": "cel"}, "agent": agent_block("cursor-cel-01", "filebeat"), "tags": ["forwarded", "cursor-audit"]}


registry.register("devtools", Generator(STREAM, _event, rate_per_min=1.6))
infra  # noqa: B018  (the estate helpers are shared; imported for symmetry with the other groups)
