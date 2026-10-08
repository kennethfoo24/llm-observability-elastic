import hmac
import logging
from pathlib import Path
from typing import Literal

from elasticsearch import Elasticsearch
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from .chat_service import ChatRequest, Deps, run_chat
from .config import Settings, get_settings
from .corpus_data import DOCS
from .cost import UnknownModel, load_prices
from .dls import load_keys
from .guardrail import Guardrail
from .guardrail_pipeline import PIPELINE_ID
from .quality_pipeline import PIPELINE_ID as QUALITY_PIPELINE_ID
from .llm_langchain import LangChainEngine
from .llm_sdk import GemmaGate, GemmaOffline, SdkEngine
from .models import get_models
from .personas import PERSONAS
from .retrieval import Retriever
from .security import install_security
from .telemetry import setup_guardrail_log_export

logger = logging.getLogger("app.main")


MAX_MESSAGE_CHARS = Settings.model_fields["max_message_chars"].default


class ChatBody(BaseModel):
    message: str
    persona: str
    model: str
    engine: Literal["sdk", "langchain"] = "langchain"

    @field_validator("message")
    @classmethod
    def _non_empty_and_bounded(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        if len(v) > MAX_MESSAGE_CHARS:
            raise ValueError("message too long")
        return v


def _default_deps(s: Settings, gate: GemmaGate) -> Deps:
    es = Elasticsearch(s.obs_es_url, api_key=s.guardrail_es_key, request_timeout=20)
    return Deps(
        retriever=Retriever(s.obs_es_url, load_keys(s.persona_keys_path), s.index_name),
        guardrail=Guardrail(es, s.injection_model_id, s.ner_model_id, s.guardrail_timeout_s),
        sdk=SdkEngine(s, gate), langchain=LangChainEngine(s, gate), models=get_models(s), gate=gate)


def default_dist(app_file: Path | None = None) -> Path:
    """Built UI location: <repo>/frontend/dist in the checkout (backend/app/main.py), /srv/frontend/dist in the image (app/main.py)."""
    app_dir = (app_file or Path(__file__)).resolve().parent
    candidates = [app_dir.parent.parent / "frontend" / "dist", app_dir.parent / "frontend" / "dist"]
    return next((c for c in candidates if (c / "index.html").exists()), candidates[0])


def create_app(deps: Deps | None = None, settings: Settings | None = None, gate=None,
               static_dir: Path | None = None) -> FastAPI:
    s = settings or get_settings()
    gate = gate or GemmaGate(s.gemma_base_url, s.gemma_api_key)
    try:
        setup_guardrail_log_export(s)
    except Exception as e:  # telemetry must never stop the app starting; log the type only (no key, no URL)
        logger.warning("guardrail log export disabled: %s", type(e).__name__)
    deps = deps or _default_deps(s, gate)
    if deps.gate is None:
        deps.gate = gate
    priced = (deps.prices if deps.prices is not None else load_prices())["models"]
    unpriced = sorted(m.model_id for m in deps.models.values() if m.model_id not in priced)
    if unpriced:
        raise RuntimeError(f"models registered without a price entry in prices.yaml: {', '.join(unpriced)}")
    # FastAPI >= 0.14x auto-adds a second OTLP exporter from OTEL_* env, which duplicates every span
    # and log next to opentelemetry-instrument; the distro owns export.
    app = FastAPI(title="LLM Observability", telemetry={"auto_configure": False},
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # FastAPI's default body echoes the offending input (the whole prompt); return field paths only.
        return JSONResponse({"error": "invalid_request",
                             "fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()]},
                            status_code=422)

    @app.middleware("http")
    async def password_gate(request: Request, call_next):
        if s.app_password and request.url.path.startswith("/api/"):
            supplied = request.headers.get("x-demo-password", "")
            if not hmac.compare_digest(supplied.encode(), s.app_password.encode()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    # Registered after the password gate so it is the outer middleware and sees the gate's 401s.
    install_security(app, s)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/config")
    def config():
        return {"kibana_url": s.obs_kibana_url.rstrip("/"),
                "security_kibana_url": s.sec_kibana_url.rstrip("/") or None, "company": "Foo Corp",
                "guardrail_models": {"injection": s.injection_model_id, "ner": s.ner_model_id},
                "guardrail_pipeline": PIPELINE_ID,
                "quality_pipeline": QUALITY_PIPELINE_ID}

    @app.get("/api/personas")
    def personas():
        total = len(DOCS)
        return [{"id": p.id, "name": p.name, "title": p.title, "total_docs": total,
                 "can_read_docs": sum(1 for d in DOCS if p.role in d["allowed_roles"])}
                for p in PERSONAS]

    @app.get("/api/models")
    def models():
        return [{"key": m.key, "label": m.label, "provider": m.provider, "model_id": m.model_id,
                 "available": gate.is_up() if m.provider == "gemma" else True}
                for m in deps.models.values()]

    @app.get("/api/health/gemma")
    def gemma_health():
        return {"up": gate.is_up()}

    @app.post("/api/chat")
    async def chat(body: ChatBody):
        if body.persona not in {p.id for p in PERSONAS}:
            return JSONResponse({"error": "unknown_persona"}, status_code=400)
        if body.model not in deps.models:
            return JSONResponse({"error": "unknown_model"}, status_code=400)
        try:
            return await run_in_threadpool(
                run_chat, ChatRequest(body.message, body.persona, body.model, body.engine), deps)
        except GemmaOffline as e:
            return JSONResponse({"error": "gemma_offline", "hint": str(e)}, status_code=503)
        except UnknownModel:
            logger.exception("model missing from prices.yaml")
            return JSONResponse({"error": "pricing_unavailable"}, status_code=500)
        except Exception as e:
            # Never echo the exception message: it can carry request content.
            logger.exception("upstream LLM error")
            return JSONResponse({"error": "upstream_error", "detail": type(e).__name__}, status_code=502)

    dist = static_dir if static_dir is not None else default_dist()
    if dist.is_dir() and (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")

    return app


def app_factory() -> FastAPI:
    return create_app()
