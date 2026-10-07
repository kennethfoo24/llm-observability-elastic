import json
import os
import random
import sys
from dataclasses import dataclass

import httpx

from .prompts import BENIGN, INJECTION, PII

MAX_REQUESTS_HARD_CAP = 5
WEIGHTS = {"benign": 0.85, "injection": 0.10, "pii": 0.05}
MODEL_WEIGHTS = {"eis-gpt-mini": 0.70, "eis-claude-haiku": 0.15, "eis-gemini-flash": 0.15}  # weighted toward the cheapest
PERSONAS = ["employee", "manager"]


@dataclass
class Request:
    kind: str
    persona: str
    model: str
    engine: str
    message: str
    prompt_id: str


def build_plan(rng: random.Random, models: list[dict], gemma_ok: bool) -> Request:
    kind = rng.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0]
    persona = rng.choice(PERSONAS)
    bank = {"benign": BENIGN[persona], "injection": INJECTION, "pii": PII}[kind]
    idx = rng.randrange(len(bank))
    available = {m["key"] for m in models if m.get("available")}
    pool = {k: w for k, w in MODEL_WEIGHTS.items() if k in available}
    if gemma_ok and "gemma" in available:
        pool["gemma"] = 0.10
    model = rng.choices(list(pool), weights=list(pool.values()))[0] if pool else "eis-gpt-mini"
    engine = "langchain" if rng.random() < 0.30 else "sdk"
    return Request(kind, persona, model, engine, bank[idx], f"{kind}-{persona if kind == 'benign' else 'any'}-{idx}")


def _emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _json_body(r: httpx.Response):
    try:
        data = r.json()
    except ValueError:
        return None
    return data


def run(client: httpx.Client, rng: random.Random, max_requests: int, password: str, gemma_ok: bool) -> list[dict]:
    headers = {"X-Demo-Password": password}
    try:
        resp = client.get("/api/models", headers=headers)
    except httpx.TransportError:
        _emit({"event": "unreachable"})
        raise SystemExit(2) from None
    if resp.status_code == 401:
        _emit({"event": "auth_failed"})
        raise SystemExit(1)
    models = _json_body(resp) if resp.status_code == 200 else None
    if not isinstance(models, list):
        models = []
    results: list[dict] = []
    for _ in range(min(max_requests, MAX_REQUESTS_HARD_CAP)):
        plan = build_plan(rng, models, gemma_ok)
        try:
            r = client.post("/api/chat", headers=headers, timeout=100.0, json={
                "message": plan.message, "persona": plan.persona, "model": plan.model, "engine": plan.engine})
        except httpx.TransportError:
            # Never include the exception text: it can carry request details.
            _emit({"event": "interrupted", "completed": len(results)})
            break
        if r.status_code == 401:
            _emit({"event": "auth_failed"})
            raise SystemExit(1)
        body = _json_body(r)
        if not isinstance(body, dict):
            body = {}
        row = {"kind": plan.kind, "prompt_id": plan.prompt_id, "persona": plan.persona, "model": plan.model,
               "engine": plan.engine, "status": r.status_code, "blocked": body.get("blocked"),
               "verdict": (body.get("guardrail") or {}).get("verdict"), "cost_usd": body.get("cost_usd")}
        results.append(row)
        _emit(row)
        if r.status_code == 429:
            break
    return results


def _max_requests() -> int:
    try:
        n = int(os.getenv("MAX_REQUESTS", "1"))
    except ValueError:
        return 1
    return max(1, min(n, MAX_REQUESTS_HARD_CAP))


def main() -> int:
    password = os.getenv("APP_PASSWORD")
    if not password:
        print("APP_PASSWORD is not set", file=sys.stderr, flush=True)
        return 1
    seed = os.getenv("SEED")
    try:
        rng = random.Random(int(seed)) if seed else random.Random()
    except ValueError:
        rng = random.Random()
    with httpx.Client(base_url=os.getenv("TARGET_URL", "http://glassbox.genai-demo.svc:80"), timeout=100.0) as client:
        run(client, rng, _max_requests(), password, os.getenv("GEMMA_TRAFFIC") == "1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
