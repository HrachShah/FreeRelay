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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from freerelay.config.settings import get_settings
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelListResponse,
)
from freerelay.core.routing.engine import RoutingEngine
from freerelay.core.routing.factory import create_routing_engine
from freerelay.observability.logging import setup_logging
from freerelay.shared.models.internal import (
    CheckoutRequest,
    CheckoutResponse,
    RegisterRequest,
    RegisterResponse,
)

logger = logging.getLogger("freerelay")

# ── Global engine reference ──────────────────────────────────────────
_engine: RoutingEngine | None = None


def get_engine() -> RoutingEngine | None:
    """Get the global routing engine. Used by health checks."""
    return _engine


# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _engine

    settings = get_settings()

    # Setup logging
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    # Build engine
    _engine = create_routing_engine(settings)

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
        from fastapi.responses import ORJSONResponse

        default_response_class: type[Response] = ORJSONResponse
    except (ImportError, OSError):
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
    if settings.enable_auth or settings.enable_supabase_auth:
        from freerelay.middleware.auth import AuthMiddleware

        app.add_middleware(
            AuthMiddleware,
            api_key=settings.api_key,
            enable_supabase=settings.enable_supabase_auth,
        )

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

    @app.get("/v1/hello")
    async def hello() -> dict[str, str]:
        return {"message": "Hello from FreeRelay!"}

    @app.get("/v1/models")
    async def list_models() -> dict[str, object]:
        engine = _engine
        if not engine:
            return ModelListResponse().model_dump()

        models = engine.get_models()
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
        except OSError:
            return JSONResponse(
                status_code=400,
                content=ChatCompletionResponse.error_body("Invalid JSON body", 400),
            )

        try:
            req = ChatCompletionRequest.model_validate_json(body)
        except (ValueError, TypeError) as e:
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

        user_id = getattr(request.state, "user_id", None)
        tier = getattr(request.state, "tier", "free")

        if req.is_streaming():
            return StreamingResponse(
                engine.route_stream(req, user_id=user_id, tier=tier),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        response = await engine.route(req, user_id=user_id, tier=tier)

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

    @app.get("/v1/analytics")
    async def analytics(request: Request, days: int = 7) -> Any:
        from freerelay.observability.analytics import get_usage_analytics

        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

        return get_usage_analytics(user_id, days=days)

    # ── Auth & Billing ───────────────────────────────────────────

    @app.post("/v1/auth/register", response_model=None)
    async def register(req: RegisterRequest) -> RegisterResponse:
        from freerelay.shared.security.crypto import generate_api_key, hash_api_key
        from freerelay.shared.tenancy.supabase import get_supabase_admin_client
        import supabase

        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        try:
            sb = get_supabase_admin_client()
            # 1. Create user (Strict insert to prevent account hijacking)
            try:
                user_res = (
                    sb.table("users")
                    .insert({"email": req.email})
                    .execute()
                )
                user_data: Any = user_res.data[0]
                user_id = str(user_data["id"])
            except (supabase.APIError, Exception):
                # User probably exists. In a production system, we would 
                # trigger an email verification or login flow here.
                # For security, we DO NOT return a new key for an existing email.
                return JSONResponse(
                    status_code=400,
                    content={"error": "User with this email already exists. Please log in."},
                )  # type: ignore

            # 2. Store hashed key
            sb.table("api_keys").insert(
                {"user_id": user_id, "key_hash": key_hash, "label": "Default Key"}
            ).execute()

            return RegisterResponse(api_key=api_key)
        except Exception as e:
            logger.exception("Registration failed")
            return JSONResponse(
                status_code=500,
                content={"error": f"Registration failed: {str(e)}"},
            )  # type: ignore

    @app.post("/v1/billing/checkout", response_model=None)
    async def billing_checkout(req: CheckoutRequest) -> CheckoutResponse:
        from freerelay.integrations.stripe import create_checkout_session

        try:
            session = create_checkout_session(req.email, req.price_id)
            return CheckoutResponse(url=session.url)
        except Exception as e:
            logger.exception("Stripe session creation failed")
            return JSONResponse(
                status_code=500,
                content={"error": f"Stripe failed: {str(e)}"},
            )  # type: ignore

    @app.post("/v1/billing/webhook")
    async def stripe_webhook(request: Request) -> Response:
        import stripe

        from freerelay.shared.tenancy.supabase import get_supabase_admin_client
        
        payload = await request.body()
        sig_header = request.headers.get("Stripe-Signature")
        settings = get_settings()

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )  # type: ignore[no-untyped-call]
        except ValueError as e:
            return Response(content=str(e), status_code=400)

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            email = session.get("customer_email")
            # Upgrade user to bronze/silver based on price_id or metadata
            # For MVP, we just set to 'bronze'
            if email:
                supabase = get_supabase_admin_client()
                supabase.table("users").update({"tier": "bronze"}).eq(
                    "email", email
                ).execute()
                logger.info(f"User {email} upgraded to bronze")

        return Response(status_code=200)

    @app.get("/metrics")
    async def metrics() -> Response:
        from freerelay.observability.metrics import (
            CONTENT_TYPE_LATEST,
            PROMETHEUS_AVAILABLE,
            generate_latest,
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

    # ── OpenClaw Integration ──────────────────────────────────────
    @app.get("/openclaw/config")
    async def openclaw_config(
        request: Request,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, object]:
        """
        Generate an OpenClaw provider config snippet.

        Query params:
          - base_url: Override the FreeRelay base URL (default: auto-detected)
          - api_key: Override the API key (default: gateway key or 'not-needed')

        Returns a JSON fragment ready to merge into ~/.openclaw/openclaw.json.
        """
        from freerelay.openclaw.adapter import OpenClawAdapter

        engine = _engine

        # Auto-detect base URL from request if not provided
        if base_url is None:
            scheme = request.url.scheme
            host = request.url.hostname or "localhost"
            port = request.url.port or settings.port
            base_url = f"{scheme}://{host}:{port}/v1"

        provider_models = engine.get_stats() if engine else []
        adapter = OpenClawAdapter(settings, provider_models)
        config = adapter.generate_config(base_url=base_url, api_key=api_key)
        setup_commands = adapter.generate_setup_commands(base_url=base_url)

        return {
            "openclaw_config": config,
            "setup_commands": setup_commands,
            "instructions": (
                "Merge 'openclaw_config' into ~/.openclaw/openclaw.json, "
                "or run one of the 'setup_commands' to configure automatically."
            ),
        }

    @app.get("/openclaw/models")
    async def openclaw_models() -> dict[str, object]:
        """
        List available models in OpenClaw-compatible format.

        This endpoint returns models in the format OpenClaw expects,
        with provider-prefixed model IDs (e.g., 'freerelay/auto').
        """
        from freerelay.openclaw.adapter import OpenClawAdapter

        engine = _engine
        provider_models = engine.get_stats() if engine else []
        adapter = OpenClawAdapter(settings, provider_models)
        models = adapter.build_models()

        return {
            "object": "list",
            "data": [
                {
                    "id": f"freerelay/{m.id}",
                    "object": "model",
                    "owned_by": "freerelay",
                    "name": m.name,
                }
                for m in models
            ],
        }

    # ── OpenCode & Codex Integration ─────────────────────────────────
    @app.get("/opencode/models")
    async def opencode_models() -> dict[str, object]:
        """
        List available OpenCode models.

        Free models (-free suffix) work without auth.
        Paid models require OPENCODE_API_KEY.
        """
        from freerelay.providers.opencode import (
            fetch_opencode_models,
            get_known_free_models,
        )

        api_key = settings.keys.opencode_api_key
        models = await fetch_opencode_models(api_key)
        if not models:
            models = get_known_free_models()

        return {
            "object": "list",
            "data": [
                {
                    "id": f"opencode/{m['id']}",
                    "object": "model",
                    "owned_by": "opencode",
                    "name": m["name"],
                    "free": m.get("free", False),
                }
                for m in models
            ],
            "auth_required": bool(api_key),
            "note": (
                "Models ending in -free work without auth. "
                "Other models require OPENCODE_API_KEY."
            ),
        }

    @app.get("/opencode/config")
    async def opencode_config(
        request: Request,
        base_url: str | None = None,
    ) -> dict[str, object]:
        """
        Generate OpenClaw config for OpenCode + Codex integration.
        """
        if base_url is None:
            scheme = request.url.scheme
            host = request.url.hostname or "localhost"
            port = request.url.port or settings.port
            base_url = f"{scheme}://{host}:{port}/v1"

        return {
            "providers": {
                "opencode": {
                    "baseUrl": base_url,
                    "apiKey": settings.keys.opencode_api_key or "",
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": "opencode/mimo-v2-pro-free",
                            "free": True,
                            "note": "No auth required",
                        },
                    ],
                    "auth_note": (
                        "Free models (-free suffix) need no API key. "
                        "Set OPENCODE_API_KEY for paid models."
                    ),
                },
                "codex": {
                    "baseUrl": base_url,
                    "api": "openai-completions",
                    "auth": {
                        "type": "oauth",
                        "provider": "chatgpt",
                        "setup": "Run 'openclaw configure' to authenticate",
                    },
                    "models": [
                        {"id": "codex/codex-mini-latest"},
                        {"id": "codex/o4-mini"},
                        {"id": "codex/gpt-4.1"},
                    ],
                },
            },
        }

    @app.get("/opencode/cli-backends")
    async def opencode_cli_backends() -> dict[str, object]:
        """
        List available CLI backends (OpenCode CLI, Codex CLI).

        Shows which backends are installed and available.
        """
        from freerelay.cli_backend import get_backend_config, list_available_backends

        return {
            "backends": list_available_backends(),
            "config": get_backend_config(),
        }

    @app.get("/codex/auth-status")
    async def codex_auth_status() -> dict[str, object]:
        """Check ChatGPT OAuth token status for Codex provider."""
        from freerelay.providers.codex import get_codex_token_status

        return get_codex_token_status()

    @app.post("/opencode/cli-run")
    async def opencode_cli_run(request: Request) -> Response:
        """
        Run a CLI backend (OpenCode/Codex) with a prompt.

        Body: {"backend": "opencode-cli", "prompt": "...", "model": "..."}
        """
        from freerelay.cli_backend import CLIBackend

        try:
            body = await request.json()
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON body"},
            )

        backend_name = body.get("backend", "opencode-cli")
        prompt = body.get("prompt", "")
        model = body.get("model")
        session_id = body.get("session_id")

        if not prompt:
            return JSONResponse(
                status_code=400,
                content={"error": "prompt is required"},
            )

        try:
            backend = CLIBackend(backend_name)
            response = await backend.run(prompt, model=model, session_id=session_id)
            return JSONResponse(content=response.model_dump(exclude_none=True))
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={"error": str(e)},
            )
        except (OSError, RuntimeError) as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"CLI backend error: {str(e)[:200]}"},
            )

    @app.get("/skills")
    async def list_skills() -> dict[str, object]:
        """
        List all available skills (OpenCode, Codex, Coding Supervisor).
        """
        from freerelay.skills import list_skills as _list_skills

        return {"skills": _list_skills()}

    @app.get("/skills/config")
    async def skills_config() -> dict[str, object]:
        """
        Get skills configuration for OpenClaw integration.
        """
        from freerelay.skills import get_skills_config

        return get_skills_config()

    return app


# ── App instance ─────────────────────────────────────────────────────
app = create_app()

# ── Run directly ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Use uvloop on Linux for better async performance
    try:
        import uvloop

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
