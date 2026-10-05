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


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float, now: Callable[[], float] = time.monotonic):
        self.limit, self.window, self._now = limit, window_s, now
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str) -> deque[float]:
        q, cutoff = self._hits[key], self._now() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def allow(self, key: str) -> bool:
        q = self._trim(key)
        if len(q) >= self.limit:
            return False
        q.append(self._now())
        return True

    def blocked(self, key: str) -> bool:
        return len(self._trim(key)) >= self.limit

    def record(self, key: str) -> None:
        self._trim(key).append(self._now())

    def retry_after(self, key: str) -> int:
        q = self._trim(key)
        return max(1, int(q[0] + self.window - self._now()) + 1) if q else 1


def client_ip(scope_client: str | None, forwarded_for: str | None, trusted_hops: int = 1) -> str:
    """The Google load balancer appends `<client>, <lb>` to X-Forwarded-For; only entries added by OUR proxy
    chain are trusted, so a client-supplied leftmost value cannot be used to evade limits."""
    if forwarded_for and trusted_hops >= 1:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        idx = len(parts) - 1 - trusted_hops
        if 0 <= idx < len(parts):
            return parts[idx]
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
        if path.startswith("/api/"):
            if auth_fail.blocked(ip):
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
