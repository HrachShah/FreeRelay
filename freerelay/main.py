"""
FreeRelay — Main FastAPI Server
==================================
Production AI gateway with:
- Full OpenAI-compatible API
- Provider rotation with circuit breakers
- Streaming with backpressure
- Health/readiness probes
- Dashboard
- Prometheus metrics endpoint
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from freerelay.config.settings import Settings, get_settings
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelListResponse,
    ModelObject,
)
from freerelay.core.routing.engine import RoutingEngine
from freerelay.observability.logging import setup_logging

logger = logging.getLogger("freerelay")

# ── Global engine reference ──────────────────────────────────────────
_engine: RoutingEngine | None = None


def get_engine() -> RoutingEngine | None:
    """Get the global routing engine. Used by health checks."""
    return _engine


def _build_engine(settings: Settings) -> RoutingEngine:
    """Build the routing engine and register providers based on mode."""
    from freerelay.providers.groq import GroqProvider
    from freerelay.providers.google import GoogleProvider
    from freerelay.providers.openrouter import OpenRouterProvider
    from freerelay.providers.together import TogetherProvider
    from freerelay.providers.mistral import MistralProvider

    engine = RoutingEngine(settings)
    keys = settings.keys
    mode = settings.mode

    # Define provider tiers
    free_providers: list[tuple[type, str, int | None]] = [
        (GroqProvider, keys.groq_api_key, 500_000),
        (GoogleProvider, keys.google_ai_key, None),
        (OpenRouterProvider, keys.openrouter_api_key, None),
        (TogetherProvider, keys.together_api_key, None),
        (MistralProvider, keys.mistral_api_key, None),
    ]

    paid_providers: list[tuple[type, str, int | None]] = []

    if keys.openai_api_key:
        from freerelay.providers.openai import OpenAIProvider

        paid_providers.append((OpenAIProvider, keys.openai_api_key, None))

    if keys.anthropic_api_key:
        from freerelay.providers.anthropic import AnthropicProvider

        paid_providers.append((AnthropicProvider, keys.anthropic_api_key, None))

    has_free = any(api_key for _, api_key, _ in free_providers)
    has_paid = any(api_key for _, api_key, _ in paid_providers)

    # Register providers based on mode
    if mode == "free":
        # Only use free providers
        for provider_cls, api_key, daily_limit in free_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="free",
                )
                has_free = True

    elif mode == "paid":
        # Only use paid providers
        for provider_cls, api_key, daily_limit in paid_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="paid",
                )

    else:  # "auto" mode - use free by default, paid for complex tasks
        # Register free providers first
        for provider_cls, api_key, daily_limit in free_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="free",
                )
                has_free = True

        # Also register paid providers for complex tasks
        for provider_cls, api_key, daily_limit in paid_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="paid",
                )
                has_paid = True

    # If no API keys configured, add demo provider
    if not has_free and not has_paid:
        from freerelay.providers.demo import DemoProvider

        engine.register_provider(
            provider=DemoProvider(),
            api_key="demo",
            daily_limit=1000,
            tier="free",
        )
        logger.info("Running in DEMO mode (no API keys configured)")

    # Log the mode
    if mode == "free":
        logger.info("Mode: FREE (using only free providers)")
    elif mode == "paid":
        logger.info("Mode: PAID (using only paid providers)")
    else:
        logger.info("Mode: AUTO (free + paid, routing decides)")

    return engine


# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _engine

    settings = get_settings()

    # Setup logging
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    # Build engine
    _engine = _build_engine(settings)

    count = len(_engine.slots)
    logger.info("=" * 56)
    logger.info("  ⚡ FreeRelay AI Gateway v0.1.0")
    logger.info(f"  Endpoint:  http://localhost:{settings.port}/v1/chat/completions")
    logger.info(f"  Dashboard: http://localhost:{settings.port}/dashboard/")
    logger.info(f"  Providers: {count} loaded")
    logger.info(f"  Chaos:     {'ON' if settings.enable_chaos else 'OFF'}")
    logger.info("=" * 56)

    if count == 0:
        logger.warning("No providers configured! Add API keys to .env")

    yield

    # Cleanup shared HTTP client
    from freerelay.shared.http_client import close_client

    await close_client()

    logger.info("FreeRelay shutting down.")


# ── App Factory ──────────────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()

    try:
        from fastapi.responses import ORJSONResponse  # type: ignore

        default_response_class = ORJSONResponse
    except Exception:
        default_response_class = JSONResponse

    app = FastAPI(
        title="FreeRelay",
        description="Production-grade AI gateway for free LLM tiers",
        version="0.1.0",
        lifespan=lifespan,
        default_response_class=default_response_class,
    )

    # CORS — allow everything (local dev proxy)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Optional auth middleware
    if settings.enable_auth and settings.api_key:
        from freerelay.middleware.auth import AuthMiddleware

        app.add_middleware(AuthMiddleware, api_key=settings.api_key)

    # Audit middleware
    from freerelay.middleware.audit import AuditMiddleware

    app.add_middleware(AuditMiddleware)

    # Rate limit middleware
    from freerelay.middleware.rate_limit import RateLimitMiddleware

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_rpm,
        burst_capacity=settings.rate_limit_burst,
    )

    # Idempotency middleware
    from freerelay.middleware.idempotency import IdempotencyMiddleware

    app.add_middleware(IdempotencyMiddleware, ttl=settings.idempotency_ttl)

    # Telemetry middleware
    if settings.enable_telemetry:
        from freerelay.middleware.telemetry import TelemetryMiddleware

        app.add_middleware(TelemetryMiddleware, enabled=True)

    # Health endpoints
    from freerelay.observability.health import router as health_router

    app.include_router(health_router)

    # ── Static Dashboard ──────────────────────────────────────────
    dashboard_dir = Path(__file__).parent.parent / "dashboard"
    if dashboard_dir.exists():
        app.mount(
            "/dashboard",
            StaticFiles(directory=str(dashboard_dir), html=True),
            name="dashboard",
        )

    # ── Routes ────────────────────────────────────────────────────

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "name": "FreeRelay",
            "version": "0.1.0",
            "status": "running",
            "docs": "/docs",
            "endpoint": "/v1/chat/completions",
            "dashboard": "/dashboard/",
        }

    @app.get("/v1/models")
    async def list_models() -> dict[str, object]:
        engine = _engine
        if not engine:
            return ModelListResponse().model_dump()

        models = [
            ModelObject(id="freerelay-auto", owned_by="freerelay"),
        ]
        for slot in engine.slots:
            models.append(
                ModelObject(
                    id=f"freerelay-{slot.provider.name}",
                    owned_by="freerelay",
                )
            )
        return ModelListResponse(data=models).model_dump()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        engine = _engine
        if not engine:
            return JSONResponse(
                status_code=503,
                content=ChatCompletionResponse.error_body(
                    "FreeRelay not initialized", 503
                ),
            )

        try:
            body = await request.body()
        except Exception:
            return JSONResponse(
                status_code=400,
                content=ChatCompletionResponse.error_body("Invalid JSON body", 400),
            )

        try:
            req = ChatCompletionRequest.model_validate_json(body)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content=ChatCompletionResponse.error_body(f"Invalid request: {e}", 400),
            )

        logger.info(
            "request",
            extra={
                "model": req.model or "auto",
                "messages": len(req.messages),
                "stream": req.is_streaming(),
            },
        )

        if req.is_streaming():
            return StreamingResponse(
                engine.route_stream(req),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        response = await engine.route(req)

        if "error" in response.model_dump():
            return JSONResponse(
                content=response.model_dump(exclude_none=True),
            )

        return JSONResponse(content=response.model_dump(exclude_none=True))

    @app.get("/v1/stats")
    async def stats() -> dict[str, object]:
        engine = _engine
        if not engine:
            return {"providers": [], "timestamp": int(time.time())}

        return {
            "providers": engine.get_stats(),
            "timestamp": int(time.time()),
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        from freerelay.observability.metrics import (
            PROMETHEUS_AVAILABLE,
            generate_latest,
            CONTENT_TYPE_LATEST,
        )

        if not PROMETHEUS_AVAILABLE:
            return Response(
                content="prometheus-client not installed",
                media_type="text/plain",
            )
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app


# ── App instance ─────────────────────────────────────────────────────
app = create_app()

# ── Run directly ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Use uvloop on Linux for better async performance
    try:
        import uvloop  # type: ignore[import-untyped]

        uvloop.install()
    except ImportError:
        pass

    settings = get_settings()
    uvicorn.run(
        "freerelay.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
