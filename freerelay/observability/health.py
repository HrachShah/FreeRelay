"""
FreeRelay — Health Endpoints (§16)
====================================
/health and /ready endpoints for orchestrators and load balancers.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """
    Liveness probe. Returns 200 if the process is alive.
    Used by Docker HEALTHCHECK, Kubernetes livenessProbe.
    """
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, object]:
    """
    Readiness probe. Returns 200 if FreeRelay is ready to serve requests.
    Checks: at least one provider configured.
    """
    # Import here to avoid circular dependency
    from freerelay.main import get_engine

    engine = get_engine()
    providers_count = len(engine.slots) if engine else 0

    if providers_count == 0:
        return {"status": "not_ready", "reason": "no_providers_configured"}

    return {"status": "ready", "providers": providers_count}
