"""NGINX (nginx access/error logs, stubstatus) and NGINX Ingress Controller (access/error logs).

Topology: 3 web hosts (web-sin-01..03) behind a load balancer; an ingress controller in front of three k8s services.
Logs are RAW lines so the package pipelines parse them; stubstatus is a final shaped metric document.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra
from .infra import GROUP, NGINX_HOSTS, S

UTC = timezone.utc
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CLIENT_IPS = ["81.2.69.142", "81.2.69.144", "81.2.69.160", "216.160.83.56", "89.160.20.112", "89.160.20.128", "2.125.160.216",
              "67.43.156.0", "175.16.199.0", "202.196.224.0", "128.101.101.101", "89.160.20.156"]
UAS = [("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", 0.34),
       ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", 0.2),
       ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", 0.16),
       ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36", 0.1),
       ("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0", 0.07),
       ("curl/8.7.1", 0.04), ("python-requests/2.32.3", 0.05), ("Googlebot/2.1 (+http://www.google.com/bot.html)", 0.02),
       ("kube-probe/1.31", 0.02)]
PATHS = [("/", 0.14), ("/api/v1/orders", 0.14), ("/api/v1/products", 0.12), ("/api/v1/cart", 0.07), ("/api/v1/users/me", 0.06),
         ("/static/app.3f2a1c.js", 0.1), ("/static/main.9bd01e.css", 0.07), ("/images/hero.webp", 0.05), ("/login", 0.04),
         ("/api/v1/search?q=laptop", 0.05), ("/checkout", 0.03), ("/healthz", 0.06), ("/favicon.ico", 0.03), ("/wp-login.php", 0.01),
         ("/api/v1/payments", 0.03)]
STATUS = [(200, 0.84), (304, 0.06), (301, 0.015), (302, 0.01), (404, 0.04), (403, 0.006), (500, 0.012), (502, 0.007), (503, 0.005), (499, 0.005)]
REFERRERS = ["-", "https://shop.example.org/", "https://www.google.com/", "https://shop.example.org/cart", "-", "-"]


def nginx_time(ts: datetime) -> str:
    return f"{ts.day:02d}/{MON[ts.month - 1]}/{ts.year}:{ts:%H:%M:%S} +0000"


def _nginx_access(c: Ctx) -> dict:
    r = c.rng
    host = infra.host_of(r.randrange(100), NGINX_HOSTS)
    ip = r.choice(CLIENT_IPS)
    path = profile.pick(r, PATHS)
    status = int(profile.pick(r, [(str(k), w) for k, w in STATUS]))
    if path in ("/healthz", "/favicon.ico") and status >= 500:
        status = 200
    method = "POST" if path.startswith(("/api/v1/orders", "/api/v1/payments", "/api/v1/cart")) and r.random() < 0.5 or path == "/login" and r.random() < 0.8 else "GET"
    size = 0 if status in (304, 301, 302) else int(r.lognormvariate(7.5, 1.1)) if path.startswith(("/api", "/static", "/images")) else int(r.lognormvariate(6.3, 0.5))
    ua = profile.pick(r, UAS)
    user = "-"
    msg = (f'{ip} - {user} [{nginx_time(c.ts)}] "{method} {path} HTTP/1.1" {status} {size} "{r.choice(REFERRERS)}" "{ua}"')
    d = infra.log_base(host, "/var/log/nginx/access.log")
    d["message"] = msg
    d["event"] = {"timezone": "+00:00"}
    return d


def _nginx_error(c: Ctx) -> dict:
    r = c.rng
    host = infra.host_of(r.randrange(100), NGINX_HOSTS)
    pid = 1000 + infra.stable(host) % 50
    conn = r.randrange(1000, 90000)
    cip = r.choice(CLIENT_IPS)
    kinds = [
        ("error", f'connect() failed (111: Connection refused) while connecting to upstream, client: {cip}, server: shop.example.org, request: "GET /api/v1/orders HTTP/1.1", upstream: "http://10.20.5.{r.randrange(10, 14)}:8080/api/v1/orders", host: "shop.example.org"', 0.2),
        ("error", f'upstream timed out (110: Connection timed out) while reading response header from upstream, client: {cip}, server: shop.example.org, request: "POST /api/v1/payments HTTP/1.1", upstream: "http://10.20.5.{r.randrange(10, 14)}:8080/api/v1/payments", host: "shop.example.org"', 0.2),
        ("warn", f'*{conn} an upstream response is buffered to a temporary file /var/cache/nginx/proxy_temp/3/04/0000000043 while reading upstream, client: {cip}, server: shop.example.org, request: "GET /api/v1/products HTTP/1.1"', 0.2),
        ("error", f'open() "/usr/share/nginx/html/wp-login.php" failed (2: No such file or directory), client: {cip}, server: shop.example.org, request: "GET /wp-login.php HTTP/1.1", host: "shop.example.org"', 0.2),
        ("notice", "signal process started", 0.05), ("warn", f'*{conn} client intended to send too large body: 2097200 bytes, client: {cip}, server: shop.example.org, request: "POST /api/v1/cart HTTP/1.1"', 0.15)]
    lvl, text, _ = r.choices(kinds, weights=[k[2] for k in kinds])[0]
    if text.startswith("*"):
        line = f"{c.ts:%Y/%m/%d %H:%M:%S} [{lvl}] {pid}#{pid}: {text}"
    else:
        line = f"{c.ts:%Y/%m/%d %H:%M:%S} [{lvl}] {pid}#{pid}: *{conn} {text}"
    d = infra.log_base(host, "/var/log/nginx/error.log")
    d["message"] = line
    d["event"] = {"timezone": "+00:00"}
    return d


def _stub(c: Ctx) -> dict:
    host = NGINX_HOSTS[c.i % len(NGINX_HOSTS)]
    r = c.rng
    d = infra.metric_base("nginx/stubstatus", host, module="nginx")
    rate = 2.0 * (1 + c.i * 0.1)  # requests per second per host
    reqs = infra.counter(c.ts, rate, f"nginx{host}")
    accepts = int(reqs * 0.62)
    active = max(1, int(r.gauss(18 + 90 * c.load, 4)))
    reading, writing = r.randint(0, 4), max(1, int(active * r.uniform(0.15, 0.35)))
    d["nginx"] = {"stubstatus": {"accepts": accepts, "active": active, "current": reqs % 1000, "dropped": 0 if r.random() > 0.03 else r.randint(1, 3),
                                 "handled": accepts, "hostname": f"{host}:80", "reading": reading, "requests": reqs, "waiting": max(0, active - reading - writing),
                                 "writing": writing}}
    d["service"] = {"address": f"http://{host}:80/server-status", "type": "nginx"}
    return d


# ---- ingress controller ---------------------------------------------------------------------------------------------------
UPSTREAMS = [("shop-web-8080", 0.4, 8080), ("shop-api-8080", 0.4, 8080), ("shop-auth-9000", 0.2, 9000)]
ING_HOST = "ingress-nginx-controller-7d9c"


def _ing_access(c: Ctx) -> dict:
    r = c.rng
    ip = r.choice(CLIENT_IPS)
    up = profile.pick(r, [(n, w) for n, w, _ in UPSTREAMS])
    port = next(p for n, _, p in UPSTREAMS if n == up)
    path = profile.pick(r, PATHS)
    status = int(profile.pick(r, [(str(k), w) for k, w in STATUS]))
    upstream_status = status if status not in (499, 304) else (200 if status == 304 else 0)
    size = 0 if status in (304, 301, 302) else int(r.lognormvariate(6.8, 0.9))
    rt = round(r.lognormvariate(-4.0, 0.7), 3)
    up_rt = round(rt * r.uniform(0.6, 0.95), 3)
    method = "POST" if r.random() < 0.18 else "GET"
    ua = profile.pick(r, UAS)
    rid = "%032x" % r.getrandbits(128)
    upip = f"10.244.{r.randrange(1, 4)}.{r.randrange(10, 40)}"
    msg = (f'{ip} - - [{nginx_time(c.ts)}] "{method} {path} HTTP/1.1" {status} {size} "{r.choice(REFERRERS)}" "{ua}" {r.randrange(120, 900)} {rt} '
           f'[default-{up}] [] {upip}:{port} {size} {up_rt} {upstream_status} {rid}')
    d = infra.log_base(ING_HOST, "/var/log/containers/ingress-nginx-controller.log")
    d["message"] = msg
    d["event"] = {"timezone": "+00:00"}
    return d


ING_ERRS = [("W", "client_config.go", 608, "Neither --kubeconfig nor --master was specified.  Using the inClusterConfig.  This might not work."),
            ("I", "main.go", 104, "Using deprecated \"k8s.io/api/networking/v1beta1\" Ingress"), ("E", "controller.go", 210, "Error obtaining Endpoints for Service \"default/shop-api\": no object matching key \"default/shop-api\" in local store"),
            ("W", "backend_ssl.go", 109, "Error obtaining X.509 certificate: unexpected error creating SSL Cert: no valid PEM formatted block found"),
            ("I", "nginx.go", 338, "NGINX configuration change - reloading"), ("W", "controller.go", 1034, "Service \"default/shop-web\" does not have any active Endpoint."),
            ("E", "queue.go", 130, "requeuing default/shop-api, err Service \"default/shop-api\" does not have any active Endpoint")]


def _ing_error(c: Ctx) -> dict:
    r = c.rng
    lvl, f, ln, text = r.choice(ING_ERRS)
    msg = f"{lvl}{c.ts:%m%d} {c.ts:%H:%M:%S}.{c.ts.microsecond:06d}       {r.randrange(5, 12)} {f}:{ln}] {text}"
    d = infra.log_base(ING_HOST, "/var/log/containers/ingress-nginx-controller.err")
    d["message"] = msg
    d["event"] = {"timezone": "+00:00"}
    return d


registry.register(
    GROUP,
    Generator(S["nginx/access"], _nginx_access, rate_per_min=11.0),
    Generator(S["nginx/error"], _nginx_error, rate_per_min=0.9),
    Generator(S["nginx/stubstatus"], _stub, mode="entities", entities=len(NGINX_HOSTS), every_min=5),
    Generator(S["nginx_ingress_controller/access"], _ing_access, rate_per_min=6.0),
    Generator(S["nginx_ingress_controller/error"], _ing_error, rate_per_min=0.5),
)
