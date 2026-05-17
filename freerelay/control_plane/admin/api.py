"""
FreeRelay — Admin API
=======================
FastAPI router for control plane administration.
Provides endpoints for tenant CRUD, policy management, experiment control,
benchmark triggers, and health status.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from freerelay.config.settings import get_settings
import redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """Verify admin bearer token."""
    settings = get_settings()
    if not settings.enable_auth:
        return "auth_disabled"

    if not settings.api_key:
        raise HTTPException(status_code=500, detail="Admin API key not configured")

    if credentials.credentials != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid admin credentials")

    return credentials.credentials


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TenantCreateRequest(BaseModel):
    namespace: str
    allowed_providers: list[str] = Field(
        default_factory=lambda: ["groq", "google", "openrouter", "together", "mistral"]
    )
    cost_ceiling: float = 100.0
    min_safety_tier: str = "medium"
    economic_policy: str = "balanced"
    pii_masking: bool = False
    audit_trail: bool = True
    rate_limit_rpm: int = 60
    max_concurrent_requests: int = 10
    preferred_models: list[str] = Field(default_factory=list)
    blocked_models: list[str] = Field(default_factory=list)
    owner: str = ""
    description: str = ""


class TenantUpdateRequest(BaseModel):
    allowed_providers: list[str] | None = None
    cost_ceiling: float | None = None
    min_safety_tier: str | None = None
    economic_policy: str | None = None
    pii_masking: bool | None = None
    audit_trail: bool | None = None
    rate_limit_rpm: int | None = None
    max_concurrent_requests: int | None = None
    preferred_models: list[str] | None = None
    blocked_models: list[str] | None = None
    owner: str | None = None
    description: str | None = None
    active: bool | None = None


class PolicyUpdateRequest(BaseModel):
    policy: dict[str, Any]
    reason: str = "admin_update"


class ExperimentCreateRequest(BaseModel):
    name: str
    type: str = "ab_routing"
    description: str = ""
    policy_a: dict[str, Any] = Field(default_factory=dict)
    policy_b: dict[str, Any] = Field(default_factory=dict)
    split_percentage: int = 50
    quality_threshold: float = 0.4
    auto_rollback: bool = True


class BenchmarkRunRequest(BaseModel):
    provider: str
    model: str
    spot_check: bool = False


class HealthResponse(BaseModel):
    status: str
    instance_id: str
    is_leader: bool
    uptime_s: float
    version: str
    components: dict[str, str]


# ---------------------------------------------------------------------------
# Lazy-loaded component references (set by the control plane startup)
# ---------------------------------------------------------------------------

_tenant_manager: Any = None
_experiment_manager: Any = None
_benchmark_engine: Any = None
_policy_publisher: Any = None
_capability_registry: Any = None
_control_plane: Any = None
_start_time: float = 0.0


def configure_admin(
    tenant_manager: Any = None,
    experiment_manager: Any = None,
    benchmark_engine: Any = None,
    policy_publisher: Any = None,
    capability_registry: Any = None,
    control_plane: Any = None,
) -> None:
    """Set component references for the admin API."""
    global _tenant_manager, _experiment_manager, _benchmark_engine
    global _policy_publisher, _capability_registry, _control_plane, _start_time

    _tenant_manager = tenant_manager
    _experiment_manager = experiment_manager
    _benchmark_engine = benchmark_engine
    _policy_publisher = policy_publisher
    _capability_registry = capability_registry
    _control_plane = control_plane
    _start_time = time.time()


# ---------------------------------------------------------------------------
# Tenant CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("/tenants", status_code=201)
async def create_tenant(
    req: TenantCreateRequest,
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new tenant policy."""
    if _tenant_manager is None:
        raise HTTPException(status_code=503, detail="Tenant manager not initialized")

    from freerelay.control_plane.admin.tenant_manager import TenantPolicy

    policy = TenantPolicy(
        namespace=req.namespace,
        allowed_providers=req.allowed_providers,
        cost_ceiling=req.cost_ceiling,
        min_safety_tier=req.min_safety_tier,
        economic_policy=req.economic_policy,
        pii_masking=req.pii_masking,
        audit_trail=req.audit_trail,
        rate_limit_rpm=req.rate_limit_rpm,
        max_concurrent_requests=req.max_concurrent_requests,
        preferred_models=req.preferred_models,
        blocked_models=req.blocked_models,
        owner=req.owner,
        description=req.description,
    )

    try:
        namespace = await _tenant_manager.create_tenant(policy)
        return {"namespace": namespace, "status": "created"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (TypeError, AttributeError) as exc:
        logger.exception("admin_create_tenant_error")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tenants")
async def list_tenants(
    active_only: bool = False,
    _auth: str = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all tenant policies."""
    if _tenant_manager is None:
        raise HTTPException(status_code=503, detail="Tenant manager not initialized")

    tenants = await _tenant_manager.list_tenants(active_only=active_only)
    return [
        {
            "namespace": t.namespace,
            "allowed_providers": t.allowed_providers,
            "cost_ceiling": t.cost_ceiling,
            "min_safety_tier": t.min_safety_tier,
            "economic_policy": t.economic_policy,
            "active": t.active,
            "owner": t.owner,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in tenants
    ]


@router.get("/tenants/{namespace}")
async def get_tenant(
    namespace: str,
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Get a specific tenant policy."""
    if _tenant_manager is None:
        raise HTTPException(status_code=503, detail="Tenant manager not initialized")

    tenant = await _tenant_manager.get_tenant(namespace)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{namespace}' not found")

    return tenant.to_dict()


@router.put("/tenants/{namespace}")
async def update_tenant(
    namespace: str,
    req: TenantUpdateRequest,
    _auth: str = Depends(require_admin),
) -> dict[str, str]:
    """Update a tenant policy."""
    if _tenant_manager is None:
        raise HTTPException(status_code=503, detail="Tenant manager not initialized")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        success = await _tenant_manager.update_tenant(namespace, updates)
        if success:
            return {"namespace": namespace, "status": "updated"}
        raise HTTPException(status_code=500, detail="Update failed")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/tenants/{namespace}")
async def delete_tenant(
    namespace: str,
    _auth: str = Depends(require_admin),
) -> dict[str, str]:
    """Delete a tenant policy."""
    if _tenant_manager is None:
        raise HTTPException(status_code=503, detail="Tenant manager not initialized")

    deleted = await _tenant_manager.delete_tenant(namespace)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tenant '{namespace}' not found")
    return {"namespace": namespace, "status": "deleted"}


# ---------------------------------------------------------------------------
# Policy management
# ---------------------------------------------------------------------------


@router.get("/policies")
async def get_policy(
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Get the current routing policy."""
    if _policy_publisher is None:
        raise HTTPException(status_code=503, detail="Policy publisher not initialized")

    policy = await _policy_publisher.load_current()
    if policy is None:
        return {"policy": None, "message": "No policy published yet"}
    return {"policy": policy}


@router.put("/policies")
async def update_policy(
    req: PolicyUpdateRequest,
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Update and publish the routing policy."""
    if _policy_publisher is None:
        raise HTTPException(status_code=503, detail="Policy publisher not initialized")

    try:
        version = await _policy_publisher.publish(req.policy, reason=req.reason)
        await _policy_publisher.snapshot_version(version)
        return {"version": version, "status": "published"}
    except redis.ResponseError as exc:
        logger.exception("admin_update_policy_error")
        raise HTTPException(status_code=500, detail=f"policy publish failed: {exc}")
    except redis.ConnectionError as exc:
        logger.exception("admin_update_policy_error")
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}")


# ---------------------------------------------------------------------------
# Experiment control
# ---------------------------------------------------------------------------


@router.post("/experiments", status_code=201)
async def create_experiment(
    req: ExperimentCreateRequest,
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new experiment."""
    if _experiment_manager is None:
        raise HTTPException(
            status_code=503, detail="Experiment manager not initialized"
        )

    from freerelay.control_plane.experiments.ab_router import (
        ExperimentConfig,
        ExperimentType,
    )

    config = ExperimentConfig(
        id="",
        type=ExperimentType(req.type),
        name=req.name,
        description=req.description,
        policy_a=req.policy_a,
        policy_b=req.policy_b,
        split_percentage=req.split_percentage,
        quality_threshold=req.quality_threshold,
        auto_rollback=req.auto_rollback,
    )

    try:
        exp_id = await _experiment_manager.create_experiment(config)
        return {"experiment_id": exp_id, "status": "created"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except redis.ResponseError as exc:
        logger.exception("admin_create_experiment_error")
        raise HTTPException(status_code=500, detail=f"experiment creation failed: {exc}")
    except redis.ConnectionError as exc:
        logger.exception("admin_create_experiment_error")
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}")


@router.get("/experiments")
async def list_experiments(
    active_only: bool = False,
    _auth: str = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List experiments."""
    if _experiment_manager is None:
        raise HTTPException(
            status_code=503, detail="Experiment manager not initialized"
        )

    experiments = await _experiment_manager.list_experiments(active_only=active_only)
    return [
        {
            "id": e.id,
            "name": e.name,
            "type": e.type.value,
            "active": e.active,
            "split_percentage": e.split_percentage,
            "created_at": e.created_at,
            "started_at": e.started_at,
        }
        for e in experiments
    ]


@router.get("/experiments/{experiment_id}")
async def get_experiment_status(
    experiment_id: str,
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Get experiment status and metrics."""
    if _experiment_manager is None:
        raise HTTPException(
            status_code=503, detail="Experiment manager not initialized"
        )

    status = await _experiment_manager.get_experiment_status(experiment_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@router.put("/experiments/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    _auth: str = Depends(require_admin),
) -> dict[str, str]:
    """Start an experiment."""
    if _experiment_manager is None:
        raise HTTPException(
            status_code=503, detail="Experiment manager not initialized"
        )

    success = await _experiment_manager.start_experiment(experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment_id": experiment_id, "status": "started"}


@router.put("/experiments/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    _auth: str = Depends(require_admin),
) -> dict[str, str]:
    """Stop an experiment."""
    if _experiment_manager is None:
        raise HTTPException(
            status_code=503, detail="Experiment manager not initialized"
        )

    success = await _experiment_manager.stop_experiment(experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment_id": experiment_id, "status": "stopped"}


# ---------------------------------------------------------------------------
# Benchmark triggers
# ---------------------------------------------------------------------------


@router.post("/benchmarks/run", status_code=202)
async def trigger_benchmark(
    req: BenchmarkRunRequest,
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger a benchmark run."""
    if _benchmark_engine is None:
        raise HTTPException(status_code=503, detail="Benchmark engine not initialized")

    import asyncio

    try:
        # Run in background
        asyncio.create_task(
            _benchmark_engine.run_suite(
                provider=req.provider,
                model=req.model,
                spot_check=req.spot_check,
            )
        )
        return {
            "provider": req.provider,
            "model": req.model,
            "mode": "spot_check" if req.spot_check else "full_suite",
            "status": "triggered",
        }
    except Exception as exc:
        logger.exception("admin_trigger_benchmark_error")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/benchmarks/results")
async def get_benchmark_results(
    provider: str,
    model: str,
    suite: str = "full_suite",
    count: int = 5,
    _auth: str = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Get recent benchmark results."""
    if _benchmark_engine is None:
        raise HTTPException(status_code=503, detail="Benchmark engine not initialized")

    return await _benchmark_engine.get_latest_results(
        provider=provider,
        model=model,
        suite_name=suite,
        count=count,
    )


# ---------------------------------------------------------------------------
# Health / Status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status(
    _auth: str = Depends(require_admin),
) -> dict[str, Any]:
    """Get control plane health status."""
    components: dict[str, str] = {
        "tenant_manager": "ok" if _tenant_manager else "not_initialized",
        "experiment_manager": "ok" if _experiment_manager else "not_initialized",
        "benchmark_engine": "ok" if _benchmark_engine else "not_initialized",
        "policy_publisher": "ok" if _policy_publisher else "not_initialized",
        "capability_registry": "ok" if _capability_registry else "not_initialized",
    }

    is_leader = False
    instance_id = "unknown"
    if _control_plane is not None:
        is_leader = getattr(_control_plane, "_is_leader", False)
        instance_id = getattr(_control_plane, "_instance_id", "unknown")

    return {
        "status": "healthy"
        if all(v == "ok" for v in components.values())
        else "degraded",
        "instance_id": instance_id,
        "is_leader": is_leader,
        "uptime_s": time.time() - _start_time,
        "version": "2.0.0",
        "components": components,
    }
