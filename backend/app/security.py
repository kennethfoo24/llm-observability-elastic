import hmac
import ipaddress
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings

CSP = ("default-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
       "style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; "
       "base-uri 'self'; form-action 'self'")
SECURITY_HEADERS = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
}
HSTS = "max-age=31536000"


MAX_KEYS = 10_000


class SlidingWindowLimiter:
    """Per-key sliding window. Memory is bounded: empty keys are deleted, lookups never create keys, and
    above MAX_KEYS a sweep drops expired keys and then the oldest-inserted ones. Eviction can only help an
    attacker who can mint unlimited distinct keys, i.e. spoof X-Forwarded-For on a path with no trusted
    proxy hop; client_ip's validation and the TRUSTED_PROXY_HOPS deployment setting narrow that case."""

    def __init__(self, limit: int, window_s: float, now: Callable[[], float] = time.monotonic,
                 max_keys: int = MAX_KEYS):
        self.limit, self.window, self._now, self.max_keys = limit, window_s, now, max_keys
        self._hits: dict[str, deque[float]] = {}

    def _trim(self, key: str) -> deque[float] | None:
        q = self._hits.get(key)
        if q is None:
            return None
        cutoff = self._now() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            del self._hits[key]
            return None
        return q

    def _enforce_cap(self) -> None:
        if len(self._hits) <= self.max_keys:
            return
        for k in list(self._hits):
            self._trim(k)
        target = self.max_keys * 9 // 10  # evict below the cap so the O(n) sweep is amortised, not per request
        while len(self._hits) > target:
            del self._hits[next(iter(self._hits))]  # dicts keep insertion order: oldest first

    def _append(self, key: str) -> None:
        q = self._trim(key)
        if q is None:
            q = self._hits[key] = deque()
        q.append(self._now())
        self._enforce_cap()

    def allow(self, key: str) -> bool:
        q = self._trim(key)
        if q is not None and len(q) >= self.limit:
            return False
        self._append(key)
        return True

    def blocked(self, key: str) -> bool:
        q = self._trim(key)
        return q is not None and len(q) >= self.limit

    def record(self, key: str) -> None:
        self._append(key)

    def retry_after(self, key: str) -> int:
        q = self._trim(key)
        return max(1, int(q[0] + self.window - self._now()) + 1) if q else 1


def client_ip(scope_client: str | None, forwarded_for: str | None, trusted_hops: int = 1) -> str:
    """The Google load balancer appends `<client>, <lb>` to X-Forwarded-For; only entries added by OUR proxy
    chain are trusted, so a client-supplied leftmost value cannot be used to evade limits. The chosen entry
    must parse as an IP address, otherwise the socket peer is used. Behind the LB (TRUSTED_PROXY_HOPS=1) the
    entry at that position is the LB contract and is accepted as is."""
    if forwarded_for and trusted_hops >= 1:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        idx = len(parts) - 1 - trusted_hops
        if 0 <= idx < len(parts):
            try:
                return str(ipaddress.ip_address(parts[idx]))
            except ValueError:
                pass
    return scope_client or "unknown"


def install_security(app: FastAPI, s: Settings) -> None:
    general = SlidingWindowLimiter(s.rate_limit_per_min, 60)
    chat = SlidingWindowLimiter(s.chat_rate_limit_per_min, 60)
    auth_fail = SlidingWindowLimiter(s.auth_fail_limit, s.auth_fail_window_s)

    def _limited(limiter: SlidingWindowLimiter, key: str) -> JSONResponse:
        return JSONResponse({"error": "rate_limited"}, status_code=429,
                            headers={"Retry-After": str(limiter.retry_after(key))})

    @app.middleware("http")
    async def guard(request: Request, call_next):
        ip = client_ip(request.client.host if request.client else None,
                       request.headers.get("x-forwarded-for"), s.trusted_proxy_hops)
        path = request.url.path
        response = None
        # Valid credentials bypass the lockout: it exists only to throttle password guessing, so the
        # owner who knows the password is never locked out by someone else's failures (or their own typos).
        authed = bool(s.app_password) and hmac.compare_digest(
            request.headers.get("x-demo-password", "").encode(), s.app_password.encode())
        if path.startswith("/api/"):
            if not authed and auth_fail.blocked(ip):
                response = _limited(auth_fail, ip)
            elif not general.allow(ip):
                response = _limited(general, ip)
            elif request.method == "POST" and path == "/api/chat" and not chat.allow(ip):
                response = _limited(chat, ip)
        if response is None:
            response = await call_next(request)
            if path.startswith("/api/") and response.status_code == 401:
                auth_fail.record(ip)
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        if request.headers.get("x-forwarded-proto") == "https":
            response.headers["strict-transport-security"] = HSTS
        return response
