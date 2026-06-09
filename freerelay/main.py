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
    # Load encrypted keystore (env vars take precedence via Pydantic settings,
    # so this is a supplementary source for keys not already in the environment)
    try:
        from freerelay.shared.security.keystore import KeyStore  # noqa: PLC0415
        _ks_keys = KeyStore().load()
        for env_var, value in _ks_keys.items():
            import os  # noqa: PLC0415
            if not os.environ.get(env_var):
                os.environ[env_var] = value
        if _ks_keys:
            logger.info("Loaded %d key(s) from encrypted keystore", len(_ks_keys))
    except Exception:
        pass  # keystore is optional

    from freerelay.providers.blackbox import BlackboxProvider
    from freerelay.providers.cerebras import CerebrasProvider
    from freerelay.providers.cloudflare import CloudflareProvider
    from freerelay.providers.cohere import CohereProvider
    from freerelay.providers.github_models import GitHubModelsProvider
    from freerelay.providers.google import GoogleProvider
    from freerelay.providers.groq import GroqProvider
    from freerelay.providers.huggingface import HuggingFaceProvider
    from freerelay.providers.kilo import KiloProvider
    from freerelay.providers.llm7 import LLM7Provider
    from freerelay.providers.mistral import MistralProvider
    from freerelay.providers.ollama_cloud import OllamaCloudProvider
    from freerelay.providers.nvidia import NVIDIAProvider
    from freerelay.providers.openrouter import OpenRouterProvider
    from freerelay.providers.pollinations import PollinationsProvider
    from freerelay.providers.together import TogetherProvider
    from freerelay.providers.zai import ZaiProvider

    engine = RoutingEngine(settings)
    keys = settings.keys
    mode = settings.mode

    # ── Free providers ────────────────────────────────────────────────
    # Tuple: (ProviderClass, api_key, daily_limit, rate_limits_dict)
    # Legacy nvidia_api_key_2: merge into comma-separated for KeyPool
    nvidia_key = keys.nvidia_api_key
    if keys.nvidia_api_key_2:
        nvidia_key = f"{keys.nvidia_api_key},{keys.nvidia_api_key_2}" if keys.nvidia_api_key else ""

    free_providers: list[tuple[type, str, int | None, dict | None]] = [
        (BlackboxProvider,    keys.blackbox_api_key,     None,      None),
        (GroqProvider,        keys.groq_api_key,         500_000,
            {"rpm": 30, "tpm": 6000, "tpd": 500_000}),
        (GoogleProvider,      keys.google_ai_key,        None,
            {"rpm": 15, "tpm": 1_000_000}),
        (OpenRouterProvider,  keys.openrouter_api_key,   None,
            {"rpm": 20}),
        (TogetherProvider,    keys.together_api_key,     None,
            {"rpm": 60}),
        (MistralProvider,     keys.mistral_api_key,      None,      None),
        (NVIDIAProvider,      nvidia_key,                None,
            {"rpm": 40}),
        # ── New providers ──────────────────────────────────────────────
        (CerebrasProvider,    keys.cerebras_api_key,     None,
            {"rpm": 30}),
        (CohereProvider,      keys.cohere_api_key,       None,      None),
        (GitHubModelsProvider, keys.github_models_token, None,
            {"rpm": 15}),
        (HuggingFaceProvider, keys.huggingface_api_key,  None,      None),
        (OllamaCloudProvider, keys.ollama_cloud_api_key, None,      None),
        (ZaiProvider,         keys.zai_api_key,          None,      None),
    ]

    # Cloudflare requires both key AND account_id
    if keys.cloudflare_api_key and keys.cloudflare_account_id:
        free_providers.append(
            (CloudflareProvider, keys.cloudflare_api_key, None, {"rpm": 30})
        )

    paid_providers: list[tuple[type, str, int | None, dict | None]] = []

    if keys.openai_api_key:
        from freerelay.providers.openai import OpenAIProvider  # noqa: PLC0415
        paid_providers.append((OpenAIProvider, keys.openai_api_key, None, None))

    if keys.anthropic_api_key:
        from freerelay.providers.anthropic import AnthropicProvider  # noqa: PLC0415
        paid_providers.append((AnthropicProvider, keys.anthropic_api_key, None, None))

    has_free = any(api_key for _, api_key, _, _ in free_providers)
    has_paid = any(api_key for _, api_key, _, _ in paid_providers)

    def _reg(provider_cls: type, api_key: str, daily_limit: int | None,
             rate_limits: dict | None, tier: str) -> None:
        if not api_key:
            return
        engine.register_provider(
            provider=provider_cls(),
            api_key=api_key,
            daily_limit=daily_limit,
            tier=tier,
            rate_limits=rate_limits,
        )

    if mode == "free":
        for pcls, ak, dl, rl in free_providers:
            _reg(pcls, ak, dl, rl, "free")
        has_free = any(ak for _, ak, _, _ in free_providers)

    elif mode == "paid":
        for pcls, ak, dl, rl in paid_providers:
            _reg(pcls, ak, dl, rl, "paid")

    else:  # auto
        for pcls, ak, dl, rl in free_providers:
            _reg(pcls, ak, dl, rl, "free")
        has_free = any(ak for _, ak, _, _ in free_providers)
        for pcls, ak, dl, rl in paid_providers:
            _reg(pcls, ak, dl, rl, "paid")
        has_paid = any(ak for _, ak, _, _ in paid_providers)

    # ── Anonymous providers (no API key required, always registered) ──────
    # Pollinations (~200 req/hr), LLM7 (100 req/hr), Kilo Gateway (:free routes)
    if mode != "paid":
        for anon_cls, rpm in [
            (PollinationsProvider, 200),
            (LLM7Provider, 100),
            (KiloProvider, 200),
        ]:
            engine.register_provider(
                provider=anon_cls(),
                api_key="anon",
                daily_limit=None,
                tier="free",
                rate_limits={"rpm": rpm},
            )
        has_free = True

    if not has_free and not has_paid:
        from freerelay.providers.demo import DemoProvider  # noqa: PLC0415
        engine.register_provider(
            provider=DemoProvider(),
            api_key="demo",
            daily_limit=1000,
            tier="free",
        )
        logger.info("Running in DEMO mode (no API keys configured)")

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

        # Extract session ID from header for sticky-session routing
        session_id: str | None = request.headers.get("X-Session-Id")

        logger.info(
            "request",
            extra={
                "model": req.model or "auto",
                "messages": len(req.messages),
                "stream": req.is_streaming(),
                "session_id": session_id,
            },
        )

        if req.is_streaming():
            return StreamingResponse(
                engine.route_stream(req, session_id=session_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        response = await engine.route(req, session_id=session_id)

        if "error" in response.model_dump():
            return JSONResponse(
                content=response.model_dump(exclude_none=True),
            )

        return JSONResponse(content=response.model_dump(exclude_none=True))

    @app.post("/v1/embeddings")
    async def embeddings(request: Request) -> Response:
        """
        OpenAI-compatible embeddings endpoint.

        Routes to the best available provider that supports embeddings
        (Cohere, Mistral, HuggingFace, OpenAI, NVIDIA, Google).
        """
        from freerelay.core.models.embeddings import EmbeddingRequest  # noqa: PLC0415

        engine = _engine
        if not engine:
            return JSONResponse(
                status_code=503,
                content={"error": {"message": "FreeRelay not initialized", "code": 503}},
            )

        try:
            body = await request.body()
            emb_req = EmbeddingRequest.model_validate_json(body)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": f"Invalid request: {e}", "code": 400}},
            )

        try:
            response = await engine.embed(emb_req)
            return JSONResponse(content=response.model_dump(exclude_none=True))
        except Exception as e:
            logger.exception("Embeddings error: %s", e)
            return JSONResponse(
                status_code=503,
                content={"error": {"message": str(e), "code": 503}},
            )

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
        except Exception:
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
        except Exception as e:
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
