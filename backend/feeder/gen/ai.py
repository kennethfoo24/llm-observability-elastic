"""Stage 1 generators: AI integrations.

claude_code (OTel events), openai_chatgpt_enterprise (8 log streams), azure_openai (logs, metrics, billing),
anthropic_metrics (usage, cost, rate_limit), openai (10 streams), anthropic (audit), gcp_vertexai (3 streams).

Log streams send RAW events (`message` = JSON text, or OTel shaped attributes for claude_code) so the package ingest
pipelines do the parsing. Metric streams send final shaped documents. Everything is derived from the committed
sample events in feeder/templates plus the entity distributions in feeder.profile.
"""
from __future__ import annotations

import copy
import functools
import json
from datetime import datetime, timedelta

from .. import catalog, profile, registry
from ..harvest import load_template
from ..registry import Ctx, Generator

GROUP = "ai"

catalog.register(
    catalog.pkg("claude_code", "0.2.2", GROUP, [("events", "claude_code.events.otel", "logs")]),
    catalog.pkg("openai_chatgpt_enterprise", "0.1.0", GROUP, [
        (d, f"openai_chatgpt_enterprise.{d}", "logs")
        for d in ("app_auth_log", "app_log", "audit_log", "auth_log", "codex_log", "codex_security_log",
                  "conversation_message", "custom_agents_log")]),
    catalog.pkg("azure_openai", "1.15.0", GROUP, [("logs", "azure_openai.logs", "logs"), ("metrics", "azure.open_ai", "metrics")]),
    catalog.pkg("anthropic_metrics", "0.4.0", GROUP, [
        ("cost", "anthropic_metrics.cost", "metrics"), ("rate_limit", "anthropic_metrics.rate_limit", "metrics"),
        ("usage", "anthropic_metrics.usage", "metrics")]),
    catalog.pkg("openai", "2.4.0", GROUP, [
        (d, f"openai.{d}", "logs")
        for d in ("audio_speeches", "audio_transcriptions", "audit", "code_interpreter_sessions", "completions",
                  "embeddings", "images", "moderations", "rate_limits", "vector_stores")]),
    catalog.pkg("anthropic", "1.1.3", GROUP, [("audit", "anthropic.audit", "logs")]),
    catalog.pkg("gcp_vertexai", "1.5.0", GROUP, [
        ("auditlogs", "gcp_vertexai.auditlogs", "logs"), ("metrics", "gcp_vertexai.metrics", "metrics"),
        ("prompt_response_logs", "gcp_vertexai.prompt_response_logs", "logs")]),
)

S = {s.key: s for s in catalog.streams(GROUP)}
# Billing rows for the Azure OpenAI Billing dashboard come from the azure billing integration (not installed here):
# there is no package template, the data stream is created by the feeder (metrics-azure.billing-default).
BILLING = catalog.Stream("azure_openai", "1.15.0", "billing", "azure.billing", "metrics", GROUP)

IPS = ["81.2.69.142", "81.2.69.144", "81.2.69.160", "216.160.83.56", "89.160.20.112", "89.160.20.128", "2.125.160.216",
       "67.43.156.0", "175.16.199.0", "202.196.224.0", "128.101.101.101"]
AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
          "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
          "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
          "python-requests/2.34.2"]
OPENAI_MODELS = {"gpt-4o-mini-2024-07-18": 0.5, "gpt-4o-2024-08-06": 0.2, "gpt-4.1-2025-04-14": 0.15, "o4-mini-2025-04-16": 0.1, "gpt-5.1-codex-max": 0.05}
PROJECTS = [("proj_support_bot", 0.5), ("proj_search_rag", 0.3), ("proj_etl_enrich", 0.2)]
WORKSPACES = [("wrkspc_01SupportOps", 0.55), ("wrkspc_01DataPlatform", 0.3), ("wrkspc_01ResearchLab", 0.15)]
ORG_ID = "00000000-0000-0000-0000-000000000001"
WS_ID = "be545252-ad04-4cfa-9ca5-deca58416151"


@functools.lru_cache(maxsize=None)
def _tpl(key: str) -> dict:
    return load_template(S[key] if key in S else BILLING)


def _orig(key: str) -> dict:
    return json.loads(_tpl(key)["event"]["original"])


def J(o) -> str:
    return json.dumps(o, separators=(",", ":"))


def msg(o: dict, **extra) -> dict:
    return {"message": J(o), **extra}


def ip_for(user: dict) -> str:
    return IPS[user["idx"] % len(IPS)]


def us(ts: datetime) -> str:
    return profile.iso(ts, micro=True)


def unix(ts: datetime) -> int:
    return int(ts.timestamp())


def sget(c: Ctx, *parts) -> "profile.random.Random":
    return profile.rng_for(c.stream.key, *parts)


# ================================ claude_code (OTel logs) ================================================================

CC_TOOLS = {"Bash": 0.22, "Read": 0.2, "Edit": 0.14, "Write": 0.05, "Grep": 0.1, "Glob": 0.07, "WebFetch": 0.03, "Task": 0.04,
            "mcp__github__search_code": 0.05, "mcp__github__get_pull_request": 0.03, "mcp__jira__get_issue": 0.03,
            "mcp__elastic__esql_query": 0.04}
CC_MODELS = {"claude-sonnet-4-20250514": 0.6, "claude-opus-4-5": 0.15, "claude-haiku-4-5": 0.25}
CC_EVENTS = {"api_request": 0.3, "tool_result": 0.27, "tool_decision": 0.27, "user_prompt": 0.07, "mcp_server_connection": 0.02,
             "permission_mode_changed": 0.015, "api_error": 0.01, "skill_activated": 0.015}
CC_COMMANDS = ["git status", "npm test", "pytest -q", "ls -la", "docker ps", "kubectl get pods", "cat package.json", "rg TODO src"]
CC_SERVERS = ["github", "jira", "elastic", "slack"]
CC_SOURCES = ["config", "user_temporary", "user_permanent", "user_reject", "hook"]


def cc_events(c: Ctx) -> dict:
    r = c.rng
    u = profile.pick_user(r, 12)
    name = profile.pick(r, CC_EVENTS)
    # sessions last ~2 hours per user so session based panels have multi event sessions
    sess = str(profile._uuid(f"sess|{u['idx']}|{int(c.ts.timestamp()) // 7200}"))
    attrs: dict = {"user.id": u["id"].replace("user-", "").ljust(64, "0")[:64], "user.account_uuid": u["uuid"], "user.email": u["email"],
                   "user.account_id": "user_" + u["id"][5:], "organization.id": ORG_ID, "session.id": sess, "terminal.type": "xterm-256color",
                   "event.name": name, "event.timestamp": us(c.ts), "event.sequence": r.randrange(0, 400),
                   "prompt.id": profile.uuid_for(r), "elastic.preserve_original_event": "true"}
    err = profile.is_error(r, 0.03)
    if name == "api_request":
        model = profile.pick(r, CC_MODELS)
        tin, tout = profile.token_pair(r, 2.0)
        attrs.update({"model": model, "cost_usd": profile.cost_usd(model, tin, tout), "duration_ms": profile.latency_ms(r, model, tout),
                      "input_tokens": tin, "output_tokens": tout, "cache_read_tokens": int(tin * r.uniform(0.2, 0.8)),
                      "cache_creation_tokens": int(tin * r.uniform(0, 0.2)), "request_id": "req_" + profile.uuid_for(r)[:20],
                      "query_source": "repl_main_thread", "speed": "normal"})
    elif name in ("tool_result", "tool_decision"):
        tool = profile.pick(r, CC_TOOLS)
        attrs["tool_name"] = tool
        params: dict = {}
        if tool.startswith("mcp__"):
            srv = tool.split("__")[1]
            params = {"mcp_server_name": srv, "mcp_tool_name": tool.split("__", 2)[2]}
            attrs["tool_name"] = "mcp_tool"
        elif tool == "Bash":
            params = {"full_command": r.choice(CC_COMMANDS)}
        elif tool in ("Read", "Edit", "Write"):
            params = {"file_path": f"/work/repo/src/{r.choice(['app', 'lib', 'api', 'ui'])}/{r.choice(['main', 'util', 'index'])}.py"}
        if params:
            attrs["tool_parameters"] = J(params)
        if name == "tool_result":
            ok = not err
            attrs.update({"success": "true" if ok else "false", "duration_ms": int(r.lognormvariate(5, 1.1)),
                          "tool_result_size_bytes": int(r.lognormvariate(7, 1)), "decision_source": profile.pick(r, {"config": 0.5, "user_temporary": 0.3, "user_permanent": 0.2}),
                          "decision_type": "accept"})
            if not ok:
                attrs.update({"error": r.choice(["permission denied", "timeout after 120s", "exit status 1", "file not found"]),
                              "error_type": r.choice(["ToolExecutionError", "TimeoutError", "FileNotFoundError"])})
        else:
            rej = r.random() < 0.12
            attrs.update({"decision": "reject" if rej else "accept",
                          "decision_source": r.choice(["user_reject"] if rej else CC_SOURCES[:3]), "source": "user"})
    elif name == "mcp_server_connection":
        ok = r.random() > 0.08
        srv = r.choice(CC_SERVERS)
        attrs.update({"server_name": srv, "mcp_server_name": srv, "status": "connected" if ok else "failed", "transport_type": r.choice(["stdio", "http", "sse"]),
                      "server_scope": "project"})
        if not ok:
            attrs.update({"error": "connection refused", "error_code": "ECONNREFUSED", "error_type": "ConnectionError"})
    elif name == "permission_mode_changed":
        attrs.update({"from_mode": "default", "to_mode": r.choice(["acceptEdits", "plan", "bypassPermissions", "default"]), "trigger": "user"})
    elif name == "api_error":
        attrs.update({"error": r.choice(["rate_limited", "overloaded", "timeout"]), "error_code": r.choice(["429", "529", "408"]),
                      "error_type": "api_error", "duration_ms": int(r.lognormvariate(7, 0.5)), "model": profile.pick(r, CC_MODELS)})
    elif name == "skill_activated":
        attrs.update({"skill.name": r.choice(["pdf", "docx", "commit", "review"]), "skill.source": "user", "invocation_trigger": "user-slash"})
    elif name == "user_prompt":
        attrs.update({"prompt_length": r.randrange(10, 600), "prompt": "[redacted]"})
    nanos = f"{c.ts.microsecond:06d}{r.randrange(0, 999):03d}"
    # ECS event.sequence is read by the Session Timeline dashboard (the pipeline only fills claude_code.events.event.sequence).
    # Note: some dashboard panels filter on unprefixed fields (decision, decision_source, status, success) that no mapping
    # defines, so they stay empty with real data too (documented in docs/feeder.md).
    root = {"event": {"sequence": attrs["event.sequence"]}}
    return {**root, "@timestamp": profile.iso(c.ts), "observed_timestamp": c.ts.strftime("%Y-%m-%dT%H:%M:%S.") + nanos + "Z",
            "resource": {"attributes": {"service.name": "claude-code", "service.version": "2.1.175", "host.arch": "arm64", "os.type": "darwin",
                                        "os.version": "25.2.0"}},
            "scope": {"name": "com.anthropic.claude_code.events", "version": "2.1.175"},
            "event_name": name, "attributes": attrs, "body": {"text": f"claude_code.{name}"}}


# ================================ OpenAI ChatGPT Enterprise =============================================================

def _cg_base(c: Ctx, typ: str, tmpl: dict) -> tuple[dict, dict]:
    u = profile.pick_user(c.rng, 20)
    d = copy.deepcopy(tmpl)
    d["event_id"] = profile.uuid_for(c.rng)
    d["type"] = typ
    d["timestamp"] = us(c.ts)
    d["principal"] = {"id": WS_ID, "type": "CHATGPT_WORKSPACE"}
    d["actor"] = {"type": "ACCOUNT_USER", "user_id": u["id"], "user_email": u["email"]}
    return d, u


def _meta_ip(c: Ctx, u: dict) -> dict:
    ip = ip_for(u)
    return {"client_ip": ip, "client_ip_details": {"country": "GB", "city": "London", "region": "England", "region_code": "ENG",
                                                   "latitude": "51.50853", "longitude": "-0.12574"},
            "client_user_agent": AGENTS[u["idx"] % len(AGENTS)], "client_ja3": profile.uuid_for(c.rng).replace("-", ""),
            "client_ja4": "t13d1713h1_ab0a1bf427ad_8537cf56674e"}


def cg_audit(c: Ctx) -> dict:
    d, u = _cg_base(c, "AUDIT_LOG", _orig("openai_chatgpt_enterprise/audit_log"))
    api = c.rng.random() < 0.35
    d["actor"] = {"type": "API_KEY", "redacted_id": "sk-...RxIA"} if api else d["actor"]
    d["action"] = profile.pick(c.rng, {"LIST_WORKSPACE_LOG_FILES": 0.3, "CREATE_API_KEY": 0.05, "USER_LOGIN": 0.2, "UPDATE_WORKSPACE_SETTINGS": 0.08,
                                       "INVITE_USER": 0.07, "EXPORT_CONVERSATIONS": 0.05, "CREATE_GPT": 0.1, "DELETE_USER": 0.02, "UPDATE_ROLE": 0.13})
    d["action_result"] = "FAILURE" if profile.is_error(c.rng, 0.04) else "SUCCESS"
    d["action_privilege"] = profile.pick(c.rng, {"ADMIN": 0.4, "USER": 0.45, "OWNER": 0.15})
    d["request_metadata"] = _meta_ip(c, u)
    return msg(d)


def cg_auth(c: Ctx) -> dict:
    d, u = _cg_base(c, "AUTH_LOG", _orig("openai_chatgpt_enterprise/auth_log"))
    act = profile.pick(c.rng, {"login_success": 0.7, "login_failed": 0.12, "logout": 0.12, "mfa_challenge": 0.06})
    d["action_data"] = {"action": act, "role": c.rng.choice(["standard-user", "admin", "owner"])}
    d["request_metadata"] = _meta_ip(c, u)
    return msg(d)


def cg_app_auth(c: Ctx) -> dict:
    d, u = _cg_base(c, "APP_AUTH_LOG", _orig("openai_chatgpt_enterprise/app_auth_log"))
    d["action"] = c.rng.choice(["link", "unlink", "refresh", "authorize"])
    d["app_id"] = "asdk_app_" + profile.uuid_for(c.rng).replace("-", "")[:32]
    d["link_id"] = "link_" + profile.uuid_for(c.rng).replace("-", "")
    return msg(d)


def cg_app(c: Ctx) -> dict:
    d, u = _cg_base(c, "APP_LOG", _orig("openai_chatgpt_enterprise/app_log"))
    app = profile.pick(c.rng, {"Slack": 0.3, "GitHub": 0.25, "Google Drive": 0.2, "Jira": 0.15, "Salesforce": 0.1})
    d["app_name"], d["app_type"] = app, c.rng.choice(["MCP", "CONNECTOR", "APP"])
    d["log_type"] = c.rng.choice(["request", "response", "error"])
    d["conversation_id"] = "c-" + profile.uuid_for(c.rng)[:18]
    meta = d.get("input", {}).get("_meta", {})
    meta["openai/userAgent"] = "ChatGPT/1.2026.183 (Mac OS X 26.5.2; arm64; build 1783607847)"
    d["input"] = {**d.get("input", {}), "_meta": meta}
    d["request_metadata"] = _meta_ip(c, u)
    return msg(d)


def cg_codex(c: Ctx) -> dict:
    d, u = _cg_base(c, "CODEX_LOG", _orig("openai_chatgpt_enterprise/codex_log"))
    d["event_type"] = profile.pick(c.rng, {"PROMPT_RESPONSE_RECEIVED": 0.4, "TOOL_CALL": 0.3, "SESSION_STARTED": 0.1, "PROMPT_SUBMITTED": 0.2})
    d["client_id"] = c.rng.choice(["CODEX_CLI", "CODEX_WEB", "CODEX_IDE"])
    d["workspace_id"] = WS_ID
    model = profile.pick(c.rng, {"gpt-5.1-codex-max": 0.7, "gpt-4.1-2025-04-14": 0.3})
    tin, tout = profile.token_pair(c.rng, 3.0)
    ev = d["event_details"]
    ev.update({"detail_type": d["event_type"], "session_id": "session-" + profile.uuid_for(c.rng)[:8], "model": model,
               "status": "failure" if profile.is_error(c.rng, 0.03) else "success", "turn_id": f"turn-{c.rng.randrange(1, 20)}",
               "token_usage": {"input_tokens": tin, "output_tokens": tout, "cached_input_tokens": tin // 4, "reasoning_output_tokens": tout // 3}})
    if d["event_type"] == "TOOL_CALL":
        ev["tool_name"] = c.rng.choice(["shell", "apply_patch", "read_file", "web_search"])
    return msg(d)


def cg_codex_sec(c: Ctx) -> dict:
    d, u = _cg_base(c, "CODEX_SECURITY_LOG", _orig("openai_chatgpt_enterprise/codex_security_log"))
    et = profile.pick(c.rng, {"SCAN_CONFIGURATION_CREATED": 0.2, "SCAN_COMPLETED": 0.3, "FINDING_STATUS_UPDATED": 0.3, "SCAN_STARTED": 0.2})
    d["event_type"], d["client_id"], d["workspace_id"] = et, c.rng.choice(["CODEX_WEB", "CODEX_CLI"]), WS_ID
    repo = c.rng.choice(["example-repo", "billing-service", "web-frontend", "data-pipeline"])
    ev = {"detail_type": et, "scan_configuration_id": f"scfg-{c.rng.randrange(1, 40)}",
          "scan_configuration_fields": {"scan_type": c.rng.choice(["secrets", "dependencies", "sast"]), "owner_id": u["id"], "workspace_id": WS_ID,
                                        "repo_id": f"repo-{c.rng.randrange(1, 12)}", "repo_url": f"https://github.com/example-org/{repo}",
                                        "environment_id": "env-mock-123", "state": "active", "lookback_days": 30}}
    if et == "FINDING_STATUS_UPDATED":
        ev["updated_fields"] = {"status": c.rng.choice(["fixed", "dismissed", "open", "triaged"])}
        ev["finding_id"] = f"CVE-2025-{c.rng.randrange(1000, 9999)}"
        ev["updated_fields"]["criticality"] = profile.pick(c.rng, {"low": 0.3, "medium": 0.35, "high": 0.25, "critical": 0.1})
    d["event_details"] = ev
    return msg(d)


def cg_conv(c: Ctx) -> dict:
    d, u = _cg_base(c, "CONVERSATION_MESSAGE", _orig("openai_chatgpt_enterprise/conversation_message"))
    author = c.rng.choice(["user", "assistant", "assistant", "tool"])
    m = d["message"]
    m.update({"id": profile.uuid_for(c.rng), "created_at": us(c.ts),
              "author": {"type": author, "client_type": c.rng.choice(["desktop_web", "mobile_web", "ios", "android", "desktop_app"])},
              "content": {"type": c.rng.choice(["text", "text", "code", "multimodal_text"]), "value": "[synthetic message]"}})
    if author == "tool":
        m["author"]["tools_used"] = c.rng.choice(["browser", "python", "image_gen", "file_search"])
    m["author"]["model"] = profile.pick(c.rng, OPENAI_MODELS)
    d["conversation"] = {"id": profile.uuid_for(c.rng), "title": c.rng.choice(["Release notes", "SQL help", "Meeting summary", "Quarterly plan", "Bug triage"]),
                         "created_at": us(c.ts - timedelta(minutes=c.rng.randrange(1, 90))), "is_pinned": False, "is_temporary_chat": False}
    return msg(d)


def cg_agents(c: Ctx) -> dict:
    d, u = _cg_base(c, "CUSTOM_AGENTS_LOG", _orig("openai_chatgpt_enterprise/custom_agents_log"))
    et = profile.pick(c.rng, {"AGENT_PUBLISHED": 0.15, "AGENT_INVOKED": 0.4, "TOOL_USED": 0.25, "SKILL_ACCESSED": 0.2})
    agent = c.rng.choice([("agent-101", "Sales Ops Agent"), ("agent-102", "IT Helpdesk Agent"), ("agent-103", "Legal Review Agent")])
    d["event_type"], d["client_id"], d["workspace_id"] = et, c.rng.choice(["AGENT_BUILDER_WEB", "CHATGPT_WEB", "API"]), WS_ID
    ev = d["event_details"]
    ev.update({"detail_type": et, "agent_id": agent[0], "access_method": c.rng.choice(["link", "store", "direct"]),
               "skill_name": c.rng.choice(["crm-guide", "policy-check", "ticket-triage"])})
    ev["agent_fields"] = {**ev.get("agent_fields", {}), "name": agent[1], "tools": {"connectors": [{"connector_id": c.rng.choice(["salesforce", "github", "jira"])}]}}
    d["event_details"] = ev
    return msg(d)


# ================================ OpenAI (usage buckets, rate limits, audit) =============================================

_USAGE = {"completions": OPENAI_MODELS, "embeddings": {"text-embedding-3-small": 0.7, "text-embedding-3-large": 0.3},
          "moderations": {"omni-moderation-2024-09-26": 1.0}, "images": {"gpt-image-1-2025-04-23": 0.6, "dall-e-3": 0.4},
          "audio_speeches": {"tts-1": 0.7, "tts-1-hd": 0.3}, "audio_transcriptions": {"whisper-1": 0.6, "gpt-4o-transcribe": 0.4},
          "code_interpreter_sessions": {}, "vector_stores": {}}


def openai_usage(kind: str):
    def build(c: Ctx) -> dict:
        t = _tpl(f"openai/{kind}")["openai"]
        base = t.get("base", {})
        r = c.rng
        start = c.ts.replace(second=0, microsecond=0)
        raw: dict = {"object": base.get("usage_object_type", f"organization.usage.{kind}.result"),
                     "project_id": profile.pick(r, PROJECTS), "start_time": unix(start), "end_time": unix(start) + 60}
        if _USAGE[kind]:
            u = profile.pick_user(r, 12)
            raw.update({"model": profile.pick(r, _USAGE[kind]), "user_id": u["id"], "api_key_id": f"key_{u['idx'] % 4:02d}abc",
                        "num_model_requests": r.randrange(1, 25)})
        body = t.get(kind, {})
        for k, v in body.items():
            if isinstance(v, bool):
                raw[k] = r.random() < 0.15
            elif isinstance(v, int):
                raw[k] = int(r.lognormvariate(6, 1.0)) if v else 0
            else:
                raw[k] = v
        if kind == "completions":
            tin, tout = profile.token_pair(r, 2.0)
            raw.update({"input_tokens": tin, "output_tokens": tout, "input_cached_tokens": tin // 3, "input_audio_tokens": 0, "output_audio_tokens": 0})
        if kind == "images":
            raw.update({"images": r.randrange(1, 6), "size": r.choice(["1024x1024", "1024x1792", "512x512"]), "source": "image.generation"})
        if kind == "code_interpreter_sessions":
            raw["num_sessions"] = r.randrange(1, 8)
        if kind == "vector_stores":
            raw["usage_bytes"] = int(r.lognormvariate(14, 1))
        return msg(raw)
    return build


def openai_rate_limits(c: Ctx) -> dict:
    t = copy.deepcopy(_tpl("openai/rate_limits")["openai"]["rate_limits"])
    models = list(OPENAI_MODELS)
    model = models[c.i % len(models)]
    proj = PROJECTS[c.i % len(PROJECTS)][0]
    scale = {"gpt-4o-mini-2024-07-18": 1.0, "gpt-4o-2024-08-06": 0.5}.get(model, 0.3)
    t.update({"collected_at": profile.iso(c.ts).replace(".000Z", "Z"), "id": f"rl_{model[:12]}_{proj[-4:]}", "model": model,
              "project_id": proj, "project_name": proj.replace("proj_", "").replace("_", " ").title(),
              "max_requests_per_1_minute": int(500 * scale * 10), "max_tokens_per_1_minute": int(200000 * scale * 10)})
    return msg(t)


def openai_audit(c: Ctx) -> dict:
    d = _orig("openai/audit")
    u = profile.pick_user(c.rng, 15)
    act = profile.pick(c.rng, {"login.succeeded": 0.45, "login.failed": 0.05, "api_key.created": 0.06, "api_key.deleted": 0.03, "project.created": 0.04,
                               "user.added": 0.05, "user.updated": 0.08, "service_account.created": 0.04, "rate_limit.updated": 0.1, "invite.sent": 0.1})
    sess = d["actor"]["session"]
    sess.update({"ip_address": ip_for(u), "user": {"email": u["email"], "id": u["id"]}, "user_agent": AGENTS[u["idx"] % len(AGENTS)]})
    d["actor"]["type"] = "session" if c.rng.random() < 0.8 else "api_key"
    if d["actor"]["type"] == "api_key":
        d["actor"] = {"type": "api_key", "api_key": {"id": "key_abc", "type": "user", "user": {"email": u["email"], "id": u["id"]}}}
        d["actor"]["session"] = {"ip_address": ip_for(u), "user_agent": "python-requests/2.34.2"}
    d.update({"effective_at": unix(c.ts), "id": "audit_log-" + profile.uuid_for(c.rng).replace("-", "")[:24], "type": act})
    return msg(d)


# ================================ Anthropic (audit, metrics) =============================================================

ANT_ACTIONS = {"claude_chat_created": 0.25, "claude_chat_viewed": 0.15, "claude_project_created": 0.05, "claude_file_uploaded": 0.1,
               "mcp_server_added": 0.04, "skill_created": 0.04, "session_started": 0.12, "role_assignment_granted": 0.03,
               "api_key_created": 0.04, "user_invited": 0.04, "claude_artifact_created": 0.08, "sso_login_succeeded": 0.06}


def anthropic_audit(c: Ctx) -> dict:
    r, u = c.rng, profile.pick_user(c.rng, 14)
    act = profile.pick(r, ANT_ACTIONS)
    d = {"id": "activity_" + profile.uuid_for(r).replace("-", "")[:20], "type": act, "created_at": profile.iso(c.ts),
         "organization_uuid": "91011112-1314-4151-6171-8191a1b1c1d1",
         "actor": {"type": "user_actor", "email_address": u["email"], "user_id": u["id"], "ip_address": ip_for(u), "user_agent": AGENTS[u["idx"] % len(AGENTS)]}}
    if act.startswith("claude_chat"):
        d["claude_chat_id"] = "claude_chat_" + profile.uuid_for(r)[:10]
    if act.startswith("mcp_server") or r.random() < 0.08:
        d["mcp_server_name"] = r.choice(["github", "jira", "elastic", "slack", "notion"])
    if act.startswith("skill") or r.random() < 0.08:
        d["skill_name"] = r.choice(["pdf", "docx", "xlsx", "brand-guidelines"])
    if profile.is_error(r, 0.02):
        d["status_code"] = 500
    return msg(d)


def am_usage(c: Ctx) -> dict:
    r = c.rng
    ws = WORKSPACES[c.i % len(WORKSPACES)][0]
    model = list(CC_MODELS)[c.i % len(CC_MODELS)]
    tin, tout = profile.token_pair(r, 40.0 * c.load + 2)
    st = c.ts
    return msg({"bucket_start_time": profile.iso(st).replace(".000Z", "Z"), "bucket_end_time": profile.iso(st + timedelta(minutes=10)).replace(".000Z", "Z"),
                "uncached_input_tokens": tin, "cache_read_input_tokens": int(tin * r.uniform(0.3, 1.2)),
                "cache_creation": {"ephemeral_5m_input_tokens": int(tin * r.uniform(0.01, 0.15)), "ephemeral_1h_input_tokens": int(tin * r.uniform(0, 0.05))},
                "output_tokens": tout, "model": model, "service_tier": r.choice(["standard", "standard", "priority", "batch"]), "workspace_id": ws,
                "inference_geo": r.choice(["us", "us", "eu"])})


def am_cost(c: Ctx) -> dict:
    r = c.rng
    ws = WORKSPACES[c.i % len(WORKSPACES)][0]
    model = list(CC_MODELS)[c.i % len(CC_MODELS)]
    tin, tout = profile.token_pair(r, 40.0 * c.load + 2)
    amount = profile.cost_usd(model, tin, tout) * 100  # cents
    st = c.ts
    label = {"claude-sonnet-4-20250514": "Claude Sonnet 4", "claude-opus-4-5": "Claude Opus 4.5", "claude-haiku-4-5": "Claude Haiku 4.5"}[model]
    return msg({"amount": f"{amount:.4f}", "bucket_start_time": profile.iso(st).replace(".000Z", "Z"),
                "bucket_end_time": profile.iso(st + timedelta(minutes=10)).replace(".000Z", "Z"), "currency": "USD",
                "description": f"{label} (US) Usage", "workspace_id": ws, "model": model, "inference_geo": r.choice(["us", "us", "eu"]),
                "cost_type": "tokens", "token_type": r.choice(["uncached_input_tokens", "output_tokens"]), "service_tier": "standard"})


def am_rate(c: Ctx) -> dict:
    groups = [(["claude-opus-4-5", "claude-opus-4-5-20251101"], 4000, 10_000_000, 800_000),
              (["claude-sonnet-4-20250514", "claude-sonnet-4-5"], 8000, 20_000_000, 1_600_000),
              (["claude-haiku-4-5"], 12000, 40_000_000, 3_200_000)]
    models, rpm, itpm, otpm = groups[c.i % len(groups)]
    return msg({"group_type": "model_group", "type": "rate_limit", "models": models,
                "limits": [{"type": "requests_per_minute", "value": rpm}, {"type": "input_tokens_per_minute_cache_aware", "value": itpm},
                           {"type": "output_tokens_per_minute", "value": otpm}]})


# ================================ Azure OpenAI ============================================================================

AZ_DEPLOY = [("gpt-chat-pilot", "gpt-35-turbo", "0301", "ChatCompletions_Create"), ("gpt4o-prod", "gpt-4o", "2024-08-06", "ChatCompletions_Create"),
             ("embed-prod", "text-embedding-3-small", "1", "Embeddings_Create")]
AZ_RES = "/SUBSCRIPTIONS/12CABCB4-86E8-404F-A3D2-1DC9982F45CA/RESOURCEGROUPS/OBS-OPENAI-SERVICE-RS/PROVIDERS/MICROSOFT.COGNITIVESERVICES/ACCOUNTS/OBS-OPENAI-TEST-01"
FILTER_CATS = ["hate", "self_harm", "sexual", "violence"]


def az_logs(c: Ctx) -> dict:
    r = c.rng
    dep = profile.pick(r, {"gpt-chat-pilot": 0.3, "gpt4o-prod": 0.55, "embed-prod": 0.15})
    model = {"gpt-chat-pilot": "gpt-35-turbo", "gpt4o-prod": "gpt-4o", "embed-prod": "text-embedding-3-small"}[dep]
    tin, tout = profile.token_pair(r)
    err = profile.is_error(r, 0.02)
    filtered = r.random() < 0.06
    dur = profile.latency_ms(r, model, tout, err)
    t0 = int((c.ts.timestamp() + 62135596800) * 1e7)  # .NET ticks
    resp: dict = {"id": "chatcmpl-" + profile.uuid_for(r)[:12], "model": model, "usage": {"prompt_tokens": tin, "completion_tokens": tout, "total_tokens": tin + tout},
                  "choices": [{"index": 0, "finish_reason": "stop", "content_filter_results": {k: {"filtered": False, "severity": "safe"} for k in FILTER_CATS}}]}
    if filtered:
        cat = r.choice(FILTER_CATS)
        resp["choices"][0]["content_filter_results"][cat] = {"filtered": True, "severity": r.choice(["medium", "high"])}
    if err:
        resp = {"error": {"code": "content_filter" if r.random() < 0.5 else "429", "message": "request blocked",
                          "innererror": {"code": "ResponsibleAIPolicyViolation", "content_filter_result": {c_: {"filtered": c_ == "violence", "severity": "high" if c_ == "violence" else "safe"} for c_ in FILTER_CATS}}}}
    props = {"apiName": "Azure OpenAI API version 2024-02-15-preview", "requestTime": t0, "requestLength": tin * 4, "responseTime": t0 + dur * 10000,
             "responseLength": tout * 4, "objectId": "", "modelDeploymentName": dep, "modelName": model, "modelVersion": "0301",
             "streamType": r.choice(["Streaming", "Non-Streaming"]), "operationName": "ChatCompletions_Create",
             "backend_request_body": J({"model": model, "messages": [{"role": "user", "content": "synthetic prompt"}], "stream": False}),
             "backend_response_body": J(resp)}
    d = {"Tenant": "eastus", "callerIpAddress": "81.2.69.***", "category": "RequestResponse", "correlationId": profile.uuid_for(r), "durationMs": dur,
         "event": "ShoeboxCallResult", "location": "eastus", "operationName": "ChatCompletions_Create", "properties": J(props), "resourceId": AZ_RES,
         "resultSignature": "400" if err else "200", "time": us(c.ts)}
    return msg(d)


def az_metrics(c: Ctx) -> dict:
    t = copy.deepcopy(_tpl("azure_openai/metrics"))
    r = c.rng
    variants = [(0, "200"), (1, "200"), (2, "200"), (1, "429")]
    di, code = variants[c.i % len(variants)]
    dep, model, ver, op = AZ_DEPLOY[di]
    n = max(1, int(r.gauss(30 * c.load + 3, 3))) if code == "200" else max(1, int(r.gauss(2, 1)))
    tin, tout = n * int(r.uniform(300, 700)), n * int(r.uniform(150, 400))
    t["azure"]["dimensions"].update({"model_deployment_name": dep, "model_name": model, "model_version": ver, "operation_name": op,
                                     "status_code": code, "stream_type": r.choice(["Streaming", "Non-Streaming"])})
    t["azure"]["open_ai"] = {"requests": {"total": n}, "generated_tokens": {"total": tout}, "processed_prompt_tokens": {"total": tin},
                             "token_transaction": {"total": tin + tout}, "active_tokens": {"total": int(r.uniform(2000, 90000))},
                             "provisioned_managed_utilization_v2": {"avg": round(min(100, r.uniform(15, 85) * (0.5 + c.load / 2)), 2)},
                             "time_to_response": {"avg": round(r.uniform(180, 900), 1)}, "context_tokens_cache_match_rate": {"avg": round(r.uniform(5, 60), 1)}}
    for k in ("agent", "ecs", "elastic_agent"):
        t.pop(k, None)
    t["event"] = {"dataset": "azure.open_ai", "module": "azure", "duration": 2216811793}
    t["metricset"] = {"name": "monitor", "period": 300000}
    return t


def az_billing(c: Ctx) -> dict:
    prods = ["Azure OpenAI - GPT-4o Input", "Azure OpenAI - GPT-4o Output", "Azure OpenAI - Embeddings", "Azure OpenAI - GPT-35 Turbo"]
    p = prods[c.i % len(prods)]
    cost = round(c.rng.uniform(0.2, 6.0) * (0.4 + c.load), 4)
    day = c.ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"azure": {"billing": {"currency": "USD", "pretax_cost": cost, "product": p, "usage_start": profile.iso(day), "usage_end": profile.iso(day + timedelta(days=1))},
                      "resource": {"type": "Microsoft.CognitiveServices", "name": "obs-openai-test-01", "group": "obs-openai-service-rs"},
                      "subscription_id": "12cabcb4-86e8-404f-a3d2-1dc9982f45ca"},
            "cloud": {"provider": "azure"}, "event": {"module": "azure"}, "service": {"type": "azure"}, "metricset": {"name": "billing", "period": 600000}}


# ================================ GCP Vertex AI ===========================================================================

GCP_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]
GCP_PROJECT = "demo-genai-project"


def _hist(r, center_ms: float) -> dict:
    bounds = [10, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
    counts = []
    for b in bounds:
        counts.append(max(0, int(r.gauss(20 if b >= center_ms / 2 and b <= center_ms * 4 else 3, 3))))
    return {"values": bounds, "counts": counts}


def gcp_metrics(c: Ctx) -> dict:
    t = copy.deepcopy(_tpl("gcp_vertexai/metrics"))
    r = c.rng
    for k in ("agent", "ecs", "elastic_agent"):
        t.pop(k, None)
    t["cloud"] = {"account": {"id": GCP_PROJECT, "name": GCP_PROJECT}, "provider": "gcp"}
    t["event"] = {"dataset": "gcp_vertexai.metrics", "module": "gcp", "duration": 913154084}
    t["metricset"] = {"name": "metrics", "period": 60000}
    n = len(GCP_MODELS)
    if c.i < n:  # publisher (Gemini) serving metrics per model
        model = GCP_MODELS[c.i]
        inv = max(1, int(r.gauss(8 * c.load + 1, 2)))
        t["gcp"] = {"labels": {"metrics": {"request_type": "shared", "type": r.choice(["input", "output"])},
                               "resource": {"location": "us-central1", "model_user_id": model, "model_version_id": "", "publisher": "google"}},
                    "vertexai": {"publisher": {"online_serving": {"token_count": inv * int(r.uniform(300, 900)), "model_invocation_count": inv,
                                                                  "consumed_throughput": inv * int(r.uniform(500, 1500)),
                                                                  "model_invocation_latencies": _hist(r, 900), "first_token_latencies": _hist(r, 300)}}}}
    else:  # prediction (custom endpoint) metrics
        ep = f"endpoint-{c.i - n + 1}"
        err = profile.is_error(r, 0.03)
        t["gcp"] = {"labels": {"metrics": {"response_code": "500" if err else "200", "method": "predict"},
                               "resource": {"location": "us-central1", "endpoint_id": ep, "model_user_id": r.choice(GCP_MODELS), "resource_container": GCP_PROJECT}},
                    "vertexai": {"prediction": {"online": {"error_count": 1 if err else 0, "prediction_count": max(1, int(r.gauss(12 * c.load + 2, 3))),
                                                           "response_count": 5, "prediction_latencies": _hist(r, 400),
                                                           "cpu": {"utilization": round(r.uniform(0.1, 0.8), 3)},
                                                           "memory": {"bytes_used": int(r.uniform(2e9, 6e9))},
                                                           "network": {"received_bytes_count": int(r.uniform(1e5, 5e6)), "sent_bytes_count": int(r.uniform(1e5, 5e6))}}}}}
    return t


def gcp_audit(c: Ctx) -> dict:
    r, u = c.rng, profile.pick_user(c.rng, 10)
    method = profile.pick(r, {"google.cloud.aiplatform.internal.PredictionService.CountTokens": 0.3, "google.cloud.aiplatform.v1.PredictionService.GenerateContent": 0.4,
                              "google.cloud.aiplatform.v1.EndpointService.CreateEndpoint": 0.05, "google.cloud.aiplatform.v1.ModelService.UploadModel": 0.05,
                              "google.cloud.aiplatform.v1.PredictionService.StreamGenerateContent": 0.2})
    model = r.choice(GCP_MODELS)
    res = f"projects/{GCP_PROJECT}/locations/us-central1/publishers/google/models/{model}"
    d = {"insertId": r.choice("abcdefghij") + profile.uuid_for(r)[:11], "logName": f"projects/{GCP_PROJECT}/logs/cloudaudit.googleapis.com%2Fdata_access",
         "severity": "INFO", "timestamp": profile.iso(c.ts), "resource": {"type": "audited_resource", "labels": {"project_id": GCP_PROJECT, "method": method, "service": "aiplatform.googleapis.com"}},
         "protoPayload": {"@type": "type.googleapis.com/google.cloud.audit.AuditLog", "serviceName": "aiplatform.googleapis.com", "methodName": method, "resourceName": res,
                          "authenticationInfo": {"principalEmail": u["email"]},
                          "authorizationInfo": [{"granted": True, "permission": "aiplatform.endpoints.predict", "permissionType": "DATA_READ", "resource": res}],
                          "requestMetadata": {"callerIp": ip_for(u), "callerSuppliedUserAgent": AGENTS[u["idx"] % len(AGENTS)] + ",gzip(gfe)"},
                          "request": {"@type": "type.googleapis.com/google.cloud.aiplatform.internal.CountTokensRequest", "endpoint": res},
                          "response": {"@type": "type.googleapis.com/google.cloud.aiplatform.internal.CountTokensResponse"}}}
    return msg(d)


def gcp_prompt(c: Ctx) -> dict:
    r = c.rng
    model = r.choice(GCP_MODELS)
    tin, tout = profile.token_pair(r)
    lat = profile.latency_ms(r, model, tout)
    return msg({"endpoint": f"projects/{GCP_PROJECT}/locations/us-central1/publishers/google/models/{model}", "deployedModelId": "", "logTime": us(c.ts),
                "modelVersion": "default", "apiMethod": "GenerateContent", "requestId": str(r.getrandbits(62)),
                "request": {"contents": [{"role": "user", "parts": [{"text": "[synthetic prompt]"}]}], "generation_config": {"temperature": 0.2, "max_output_tokens": 8192}},
                "response": {"candidates": [{"content": {"role": "model", "parts": [{"text": "[synthetic response]"}]}, "finish_reason": "STOP"}],
                             "usage_metadata": {"prompt_token_count": tin, "candidates_token_count": tout, "total_token_count": tin + tout}, "model_version": model},
                "metadata": {"request_latency": lat}})


# ================================ registration ============================================================================

def _g(key: str, build, rate: float = 1.0, **kw) -> Generator:
    return Generator(S[key], build, rate_per_min=rate, **kw)


# rates are per minute at load 1.0 (average load is about 0.5): whole group ~ 12 docs/min at load 1.0
registry.register(
    GROUP,
    _g("claude_code/events", cc_events, 3.0),
    _g("openai_chatgpt_enterprise/audit_log", cg_audit, 0.25),
    _g("openai_chatgpt_enterprise/auth_log", cg_auth, 0.3),
    _g("openai_chatgpt_enterprise/app_auth_log", cg_app_auth, 0.15),
    _g("openai_chatgpt_enterprise/app_log", cg_app, 0.3),
    _g("openai_chatgpt_enterprise/codex_log", cg_codex, 0.5),
    _g("openai_chatgpt_enterprise/codex_security_log", cg_codex_sec, 0.15),
    _g("openai_chatgpt_enterprise/conversation_message", cg_conv, 0.5),
    _g("openai_chatgpt_enterprise/custom_agents_log", cg_agents, 0.25),
    _g("openai/completions", openai_usage("completions"), 0.7),
    _g("openai/embeddings", openai_usage("embeddings"), 0.3),
    _g("openai/moderations", openai_usage("moderations"), 0.25),
    _g("openai/images", openai_usage("images"), 0.15),
    _g("openai/audio_speeches", openai_usage("audio_speeches"), 0.12),
    _g("openai/audio_transcriptions", openai_usage("audio_transcriptions"), 0.12),
    _g("openai/code_interpreter_sessions", openai_usage("code_interpreter_sessions"), 0.12),
    _g("openai/vector_stores", openai_usage("vector_stores"), 0.12),
    _g("openai/rate_limits", openai_rate_limits, mode="entities", entities=len(OPENAI_MODELS), every_min=15),
    _g("openai/audit", openai_audit, 0.2),
    _g("anthropic/audit", anthropic_audit, 0.5),
    _g("anthropic_metrics/usage", am_usage, mode="entities", entities=len(WORKSPACES) * 1, every_min=10),
    _g("anthropic_metrics/cost", am_cost, mode="entities", entities=len(WORKSPACES) * 1, every_min=10),
    _g("anthropic_metrics/rate_limit", am_rate, mode="entities", entities=3, every_min=30),
    _g("azure_openai/logs", az_logs, 1.0),
    _g("azure_openai/metrics", az_metrics, mode="entities", entities=4, every_min=5),
    Generator(BILLING, az_billing, mode="entities", entities=4, every_min=10),
    _g("gcp_vertexai/auditlogs", gcp_audit, 0.25),
    _g("gcp_vertexai/metrics", gcp_metrics, mode="entities", entities=len(GCP_MODELS) + 2, every_min=5),
    _g("gcp_vertexai/prompt_response_logs", gcp_prompt, 0.3),
)
