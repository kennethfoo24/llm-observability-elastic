"""Realistic, deterministic traffic shape: day/night and weekday patterns, slow ramps, entity distributions,
1-3 percent errors and correlated tokens / cost / latency. Everything is seeded so a tick is reproducible."""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
TZ_OFFSET_H = 8  # shape the working day in Singapore time (UTC+8)


def rng_for(*parts: object) -> random.Random:
    """Deterministic Random from arbitrary parts (stream key, minute, ...)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def activity(ts: datetime) -> float:
    """Relative load 0.03..1.5: busy 09-18 local on weekdays, quiet nights, light weekends, slow 14-day wave."""
    local = ts.astimezone(UTC) + timedelta(hours=TZ_OFFSET_H)
    h = local.hour + local.minute / 60
    day = 0.04 + 0.96 * math.exp(-((h - 13.5) ** 2) / (2 * 3.2 ** 2))  # smooth bump centred on 13:30
    if h > 19:
        day += 0.15 * math.exp(-(h - 19) / 2)  # evening tail
    week = 1.0 if local.weekday() < 5 else 0.22
    wave = 1 + 0.12 * math.sin(2 * math.pi * (ts.timestamp() / 86400) / 14)  # slow ramp up and down
    return max(0.03, day * week * wave * 1.5)


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(rng.gauss(lam, math.sqrt(lam)) + 0.5))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def pick(rng: random.Random, dist: dict[str, float] | list[tuple[str, float]]) -> str:
    items = list(dist.items()) if isinstance(dist, dict) else list(dist)
    return rng.choices([k for k, _ in items], weights=[w for _, w in items])[0]


def zipf_weights(n: int, s: float = 1.1) -> list[float]:
    return [1 / (i + 1) ** s for i in range(n)]


def is_error(rng: random.Random, rate: float = 0.02) -> bool:
    return rng.random() < rate


# --- entities --------------------------------------------------------------------------------------------------------

ORGS = [("org-acme-ai", 0.6), ("org-globex-labs", 0.3), ("org-initech-data", 0.1)]
FIRST = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan", "judy", "ken", "lena", "mallory",
         "nina", "oscar", "peggy", "quinn", "rosa", "sam", "tina"]
LAST = ["martin", "chen", "novak", "okafor", "ito", "silva", "haddad", "kowalski", "reyes", "tan"]
DOMAIN = "example.org"


def users(n: int = 20) -> list[dict]:
    """Stable synthetic users, zipf weighted (a few heavy users)."""
    ws = zipf_weights(n)
    out = []
    for i in range(n):
        first, last = FIRST[i % len(FIRST)], LAST[i % len(LAST)]
        out.append({"name": f"{first}.{last}", "email": f"{first}.{last}@{DOMAIN}", "weight": ws[i],
                    "id": "user-" + hashlib.sha1(f"u{i}".encode()).hexdigest()[:22],
                    "uuid": str(_uuid(f"user{i}")), "ip": f"81.2.69.{140 + i}", "idx": i})
    return out


def _uuid(seed: str):
    import uuid
    return uuid.UUID(hashlib.md5(seed.encode()).hexdigest())  # noqa: S324 (not security relevant)


def uuid_for(rng: random.Random) -> str:
    import uuid
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def pick_user(rng: random.Random, n: int = 20) -> dict:
    us = users(n)
    return rng.choices(us, weights=[u["weight"] for u in us])[0]


# --- models, tokens, cost, latency ----------------------------------------------------------------------------------

# model -> (usd per 1M input tokens, usd per 1M output tokens, relative speed in tokens/s)
PRICES = {
    "gpt-4o-mini-2024-07-18": (0.15, 0.60, 120), "gpt-4o-2024-08-06": (2.50, 10.0, 70), "gpt-4.1-2025-04-14": (2.0, 8.0, 80),
    "gpt-5.1-codex-max": (1.25, 10.0, 60), "o4-mini-2025-04-16": (1.10, 4.40, 55),
    "claude-sonnet-4-20250514": (3.0, 15.0, 65), "claude-opus-4-5": (5.0, 25.0, 40), "claude-haiku-4-5": (1.0, 5.0, 150),
    "gemini-2.5-pro": (1.25, 10.0, 70), "gemini-2.5-flash": (0.30, 2.50, 180), "gemini-2.0-flash": (0.10, 0.40, 190),
    "text-embedding-3-small": (0.02, 0.0, 1000), "text-embedding-3-large": (0.13, 0.0, 800),
}


def token_pair(rng: random.Random, heavy: float = 1.0) -> tuple[int, int]:
    """Log-normal prompt size and a loosely correlated completion size."""
    tin = max(5, int(rng.lognormvariate(6.0, 0.9) * heavy))
    tout = max(3, int(tin * rng.uniform(0.15, 0.9) * rng.lognormvariate(0, 0.3)))
    return tin, tout


def cost_usd(model: str, tin: int, tout: int) -> float:
    pi, po, _ = PRICES.get(model, (1.0, 4.0, 80))
    return round((tin * pi + tout * po) / 1e6, 8)


def latency_ms(rng: random.Random, model: str, tout: int, error: bool = False) -> int:
    """Time to first token plus decode time (output tokens over model speed), with tail jitter."""
    speed = PRICES.get(model, (0, 0, 80))[2]
    base = 250 + tout / speed * 1000
    v = base * rng.lognormvariate(0, 0.35)
    return int(v * (0.3 if error else 1.0))


def minute_floor(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def iso(ts: datetime, micro: bool = False) -> str:
    ts = ts.astimezone(UTC)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if micro else ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"
