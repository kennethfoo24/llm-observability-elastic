"""GitLab (package `gitlab`): the Rails API and production logs, application, audit and auth logs, Pages and Sidekiq.

One fictional self-managed instance (gitlab-01) used by a 20 person engineering team. Every stream sends the RAW JSON log line as
`message`; the package pipeline parses it into ECS. The JSON for each stream starts from the package's own sample line (so all the
fields the real GitLab writes are present) and the generator replaces the interesting ones: time, user, project, path, status,
duration and source IP.
"""
from __future__ import annotations

import json
import uuid

from .. import profile, registry
from ..registry import Ctx, Generator
from . import devtools
from .devtools import S, J
from .infra import log_base

HOST = "gitlab-01"
USERS = [(1, "root"), (2, "alice"), (3, "bob"), (4, "carol"), (5, "dave"), (6, "erin"), (7, "frank"), (8, "grace"), (9, "heidi"), (10, "ivan"),
         (11, "judy"), (12, "ken"), (13, "lena"), (14, "mallory"), (15, "nina"), (16, "oscar"), (17, "peggy"), (18, "quinn"), (19, "rosa"), (20, "sam")]
PROJECTS = [("platform/payments-api", 101), ("platform/auth-service", 102), ("platform/web-frontend", 103), ("data/etl-pipelines", 104),
            ("infra/terraform-modules", 105), ("mobile/ios-app", 106), ("mobile/android-app", 107), ("docs/handbook", 108)]
IPS = ["81.2.69.142", "81.2.69.144", "81.2.69.160", "216.160.83.56", "89.160.20.112", "89.160.20.128", "2.125.160.216", "67.43.156.0", "175.16.199.0",
       "202.196.224.0", "128.101.101.101", "89.160.20.156"]
UAS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", "git/2.46.0", "GitLab-Runner 17.5.0",
       "Go-http-client/1.1", "python-gitlab/4.10.0", "curl/8.7.1"]
SEV = [("INFO", 0.95), ("WARN", 0.04), ("ERROR", 0.01)]


@devtools.functools.lru_cache(maxsize=None)
def _base(key: str) -> dict:
    return json.loads(devtools.sample(key)["event"]["original"])


def _line(key: str, ts, **over) -> dict:
    o = json.loads(json.dumps(_base(key)))
    o["time"] = profile.iso(ts)
    o.update(over)
    return o


def _raw(key: str, obj: dict, path: str) -> dict:
    d = log_base(HOST, path)
    d["message"] = J(obj)
    return d


def _user(r) -> tuple[int, str]:
    return r.choice(USERS)


def _project(r) -> tuple[str, int]:
    return r.choice(PROJECTS)


API = [("GET", "/api/v4/projects/{pid}/merge_requests", "/api/:version/projects/:id/merge_requests", "code_review_workflow", 0.2),
       ("GET", "/api/v4/projects/{pid}/pipelines", "/api/:version/projects/:id/pipelines", "continuous_integration", 0.2),
       ("GET", "/api/v4/projects/{pid}/repository/commits", "/api/:version/projects/:id/repository/commits", "source_code_management", 0.15),
       ("POST", "/api/v4/projects/{pid}/pipeline", "/api/:version/projects/:id/pipeline", "continuous_integration", 0.04),
       ("GET", "/api/v4/user", "/api/:version/user", "system_access", 0.1), ("GET", "/api/v4/runners", "/api/:version/runners", "runner", 0.06),
       ("PUT", "/api/v4/projects/{pid}/merge_requests/{n}", "/api/:version/projects/:id/merge_requests/:merge_request_iid", "code_review_workflow", 0.04),
       ("GET", "/api/v4/projects/{pid}/jobs/{n}/trace", "/api/:version/projects/:id/jobs/:job_id/trace", "continuous_integration", 0.08),
       ("GET", "/api/v4/version", "/api/:version/version", "system_access", 0.03), ("POST", "/api/v4/jobs/request", "/api/:version/jobs/request", "runner", 0.1)]


def _api(c: Ctx) -> dict:
    r = c.rng
    m, path, route, cat, _ = r.choices(API, weights=[a[4] for a in API])[0]
    uid, uname = _user(r)
    proj, pid = _project(r)
    ip = r.choice(IPS)
    status = r.choices([200, 201, 204, 304, 400, 401, 403, 404, 409, 422, 500], weights=[70, 6, 3, 8, 1.5, 2, 1.5, 4, 0.6, 0.6, 0.8])[0]
    dur = round(r.lognormvariate(-3.6, 0.9), 5)
    over = {"severity": profile.pick(r, SEV), "duration_s": dur, "view_duration_s": round(dur * 0.8, 5), "status": status, "method": m,
            "path": path.format(pid=pid, n=r.randrange(1, 2500)), "route": route, "remote_ip": ip, "meta.remote_ip": ip, "ua": r.choice(UAS),
            "user_id": uid, "username": uname, "meta.user": uname, "meta.user_id": uid, "meta.project": proj, "meta.root_namespace": proj.split("/")[0],
            "meta.caller_id": f"{m} {route}", "meta.feature_category": cat, "meta.client_id": f"user/{uid}", "correlation_id": str(uuid.UUID(int=r.getrandbits(128), version=4)),
            "pid": 1000 + r.randrange(0, 40), "worker_id": f"puma_{r.randrange(0, 6)}", "host": "gitlab.corp.example.org"}
    return _raw("gitlab/api", _line("gitlab/api", c.ts, **over), "/var/log/gitlab/gitlab-rails/api_json.log")


PROD = [("GET", "/{proj}", "Projects::ProjectsController", "show", "projects", 0.2), ("GET", "/{proj}/-/merge_requests", "Projects::MergeRequestsController", "index", "code_review_workflow", 0.2),
        ("GET", "/{proj}/-/pipelines/{n}", "Projects::PipelinesController", "show", "continuous_integration", 0.15), ("GET", "/{proj}/-/jobs/{n}", "Projects::JobsController", "show", "continuous_integration", 0.1),
        ("GET", "/", "RootController", "index", "groups_and_projects", 0.1), ("GET", "/dashboard/todos", "Dashboard::TodosController", "index", "team_planning", 0.06),
        ("POST", "/users/sign_in", "SessionsController", "create", "system_access", 0.05), ("GET", "/{proj}/-/blob/main/README.md", "Projects::BlobController", "show", "source_code_management", 0.14)]


def _prod(c: Ctx) -> dict:
    r = c.rng
    m, path, ctrl, act, cat, _ = r.choices(PROD, weights=[p[5] for p in PROD])[0]
    uid, uname = _user(r)
    proj, _pid = _project(r)
    ip = r.choice(IPS)
    status = r.choices([200, 302, 304, 404, 422, 500], weights=[78, 10, 5, 4, 1.5, 1.5])[0]
    dur = round(r.lognormvariate(-2.2, 0.8), 4)
    over = {"method": m, "path": path.format(proj=proj, n=r.randrange(1, 9000)), "controller": ctrl, "action": act, "status": status, "duration_s": dur, "view_duration_s": round(dur * 0.6, 4),
            "remote_ip": ip, "meta.remote_ip": ip, "ua": r.choice(UAS[:1] + UAS[3:4]), "user_id": uid, "username": uname, "meta.user": uname, "meta.user_id": uid,
            "meta.project": proj, "meta.caller_id": f"{ctrl}#{act}", "meta.feature_category": cat, "meta.client_id": f"user/{uid}",
            "correlation_id": str(uuid.UUID(int=r.getrandbits(128), version=4)), "pid": 800 + r.randrange(0, 40), "worker_id": f"puma_{r.randrange(0, 6)}", "format": "html"}
    if status == 302:
        over["location"] = f"https://gitlab.corp.example.org/{proj}"
    return _raw("gitlab/production", _line("gitlab/production", c.ts, **over), "/var/log/gitlab/gitlab-rails/production_json.log")


APP_MSGS = [("Successful Login: username={u} ip={ip}", 0.28), ("Failed Login: username={u} ip={ip}", 0.04), ("User Logout: username={u} ip={ip}", 0.1),
            ('{u} created a new project "{proj}"', 0.04), ('Project "{proj}" was deleted', 0.01), ("User {u2} was created", 0.015), ("User {u2} was removed", 0.006),
            ("Group {grp} was created", 0.012), ("Group {grp} was removed", 0.005), ("Updating statistics for project {pid}", 0.12), ("Mirror update finished for {proj}", 0.08),
            ("Housekeeping scheduled for project {pid}", 0.07), ("Webhook delivery succeeded for {proj}", 0.1), ("Mergeability checks finished for merge request !{n}", 0.12)]
GROUPS = ["platform", "data", "infra", "mobile", "docs", "security-reviews", "interns-2026"]


def _app(c: Ctx) -> dict:
    r = c.rng
    uid, uname = _user(r)
    proj, pid = _project(r)
    ip = r.choice(IPS)
    tmpl = profile.pick(r, APP_MSGS)
    msg = tmpl.format(u=uname, u2=r.choice(USERS)[1] + str(r.randrange(2, 90)), ip=ip, proj=proj, grp=r.choice(GROUPS), pid=pid, n=r.randrange(1, 900))
    sev = "WARN" if tmpl.startswith("Failed Login") else profile.pick(r, SEV)
    over = {"severity": sev, "meta.user": uname, "meta.user_id": uid, "meta.project": proj, "meta.root_namespace": proj.split("/")[0], "meta.remote_ip": ip, "meta.client_id": f"user/{uid}",
            "meta.caller_id": r.choice(["ProjectCacheWorker", "PipelineProcessWorker", "Projects::HousekeepingService", "NewMergeRequestWorker"]),
            "correlation_id": uuid.UUID(int=r.getrandbits(128), version=4).hex[:26].upper(), "message": msg}
    if "Mergeability" in msg or r.random() < 0.15:
        over["mergeability_merge_request_id"] = r.randrange(1, 900)
        over["mergeability_project_id"] = pid
    return _raw("gitlab/application", _line("gitlab/application", c.ts, **over), "/var/log/gitlab/gitlab-rails/application_json.log")


AUDIT = [("visibility", "Private", "Internal"), ("visibility", "Internal", "Public"), ("name", "legacy-service", "legacy-service-archive"), ("path", "old-path", "new-path"),
         ("access_level", "Developer", "Maintainer"), ("membership", "-", "Developer"), ("push_rules", "off", "on"), ("branch_protection", "off", "on")]


def _audit(c: Ctx) -> dict:
    r = c.rng
    uid, uname = _user(r)
    proj, pid = _project(r)
    ch, frm, to = r.choice(AUDIT)
    over = {"severity": "INFO", "author_id": uid, "author_name": uname, "entity_id": pid, "entity_type": r.choice(["Project", "Project", "Group", "User"]), "change": ch, "from": frm, "to": to,
            "target_id": pid, "target_type": "Project", "target_details": proj, "correlation_id": uuid.UUID(int=r.getrandbits(128), version=4).hex[:26].upper(), "meta.remote_ip": r.choice(IPS)}
    return _raw("gitlab/audit", _line("gitlab/audit", c.ts, **over), "/var/log/gitlab/gitlab-rails/audit_json.log")


def _auth(c: Ctx) -> dict:
    r = c.rng
    env = r.choices(["blocklist", "throttle", "track"], weights=[3, 5, 2])[0]
    uid, _u = _user(r)
    over = {"severity": "ERROR" if env != "track" else "WARN", "message": "Rack_Attack", "env": env, "remote_ip": r.choice(IPS), "request_method": r.choice(["GET", "POST", "GET"]),
            "path": r.choice(["/users/sign_in", "/api/v4/session", "/group/project.git/info/refs?service=git-upload-pack", "/-/profile/personal_access_tokens", "/api/v4/projects"]),
            "user_id": uid, "matched": env, "correlation_id": uuid.UUID(int=r.getrandbits(128), version=4).hex[:26].upper(), "status": r.choice([429, 429, 403])}
    return _raw("gitlab/auth", _line("gitlab/auth", c.ts, **over), "/var/log/gitlab/gitlab-rails/auth_json.log")


PAGES = ["Request completed", "Domain config loaded", "Artifact served", "Serving from the disk cache", "ACME challenge answered"]


def _pages(c: Ctx) -> dict:
    r = c.rng
    obj = json.loads(json.dumps(_base("gitlab/pages")))
    obj.update({"level": r.choices(["info", "warning", "error"], weights=[90, 8, 2])[0], "msg": r.choice(PAGES), "time": profile.iso(c.ts), "revision": "52b2899", "version": "17.5.0"})
    d = log_base(HOST, "/var/log/gitlab/gitlab-pages/current")
    d["message"] = J(obj)
    return d


WORKERS = [("UpdateAllMirrorsWorker", "cronjob:update_all_mirrors", 0.1), ("PipelineProcessWorker", "pipeline_processing:pipeline_process", 0.25), ("Ci::BuildFinishedWorker", "pipeline_processing:ci_build_finished", 0.2),
           ("ProjectCacheWorker", "default", 0.1), ("WebHookWorker", "web_hook", 0.15), ("NewMergeRequestWorker", "new_merge_request", 0.1), ("ExpireJobCacheWorker", "pipeline_cache", 0.1)]


def _sidekiq(c: Ctx) -> dict:
    r = c.rng
    cls, queue, _ = r.choices(WORKERS, weights=[w[2] for w in WORKERS])[0]
    jid = f"{r.getrandbits(96):024x}"
    dur = round(r.lognormvariate(-1.2, 1.0), 3)
    status = r.choices(["done", "fail"], weights=[96.5, 3.5])[0]
    over = {"severity": "INFO" if status == "done" else "WARN", "queue": queue, "class": cls, "queue_namespace": queue.split(":")[0], "jid": jid, "job_status": status, "duration": dur,
            "message": f"{cls} JID-{jid}: {status}: {dur} sec", "pid": 10000 + r.randrange(0, 30), "worker_id": f"sidekiq_{r.randrange(0, 4)}", "enqueued_at": profile.iso(c.ts), "created_at": profile.iso(c.ts),
            "completed_at": profile.iso(c.ts)}
    obj = _line("gitlab/sidekiq", c.ts, **over)
    d = log_base(HOST, "/var/log/gitlab/sidekiq/current")
    d["message"] = J(obj)
    return d


registry.register(
    "devtools",
    Generator(S["gitlab/api"], _api, rate_per_min=3.0), Generator(S["gitlab/production"], _prod, rate_per_min=2.5), Generator(S["gitlab/application"], _app, rate_per_min=1.0),
    Generator(S["gitlab/audit"], _audit, rate_per_min=0.35), Generator(S["gitlab/auth"], _auth, rate_per_min=0.45), Generator(S["gitlab/pages"], _pages, rate_per_min=0.2),
    Generator(S["gitlab/sidekiq"], _sidekiq, rate_per_min=1.8),
)
