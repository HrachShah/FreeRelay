"""
FreeRelay — Tenant Manager
=============================
CRUD operations for tenant policies backed by Redis.
Validates against DSL schema and provides defaults.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

TENANT_KEY_PREFIX = "freerelay:tenant"

VALID_PROVIDERS = {"groq", "google", "openrouter", "together", "mistral"}
VALID_SAFETY_TIERS = {"low", "medium", "high", "maximum"}
VALID_ECONOMIC_POLICIES = {"cost_optimized", "balanced", "quality_first"}


@dataclass
class TenantPolicy:
    """Policy configuration for a tenant namespace."""

    namespace: str
    allowed_providers: list[str] = field(default_factory=lambda: list(VALID_PROVIDERS))
    cost_ceiling: float = 100.0  # max $/day
    min_safety_tier: str = "medium"  # low | medium | high | maximum
    economic_policy: str = "balanced"  # cost_optimized | balanced | quality_first
    pii_masking: bool = False
    audit_trail: bool = True
    rate_limit_rpm: int = 60
    max_concurrent_requests: int = 10
    preferred_models: list[str] = field(default_factory=list)
    blocked_models: list[str] = field(default_factory=list)
    custom_routing_rules: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    owner: str = ""
    description: str = ""
    active: bool = True

    @property
    def key(self) -> str:
        return f"{TENANT_KEY_PREFIX}:{self.namespace}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "allowed_providers": json.dumps(self.allowed_providers),
            "cost_ceiling": str(self.cost_ceiling),
            "min_safety_tier": self.min_safety_tier,
            "economic_policy": self.economic_policy,
            "pii_masking": str(self.pii_masking),
            "audit_trail": str(self.audit_trail),
            "rate_limit_rpm": str(self.rate_limit_rpm),
            "max_concurrent_requests": str(self.max_concurrent_requests),
            "preferred_models": json.dumps(self.preferred_models),
            "blocked_models": json.dumps(self.blocked_models),
            "custom_routing_rules": json.dumps(self.custom_routing_rules),
            "created_at": str(self.created_at),
            "updated_at": str(self.updated_at),
            "owner": self.owner,
            "description": self.description,
            "active": str(self.active),
        }

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> TenantPolicy:
        """Hydrate from Redis hash data."""
        return cls(
            namespace=data.get("namespace", ""),
            allowed_providers=json.loads(data.get("allowed_providers", "[]")),
            cost_ceiling=float(data.get("cost_ceiling", 100.0)),
            min_safety_tier=data.get("min_safety_tier", "medium"),
            economic_policy=data.get("economic_policy", "balanced"),
            pii_masking=data.get("pii_masking", "False") == "True",
            audit_trail=data.get("audit_trail", "True") == "True",
            rate_limit_rpm=int(data.get("rate_limit_rpm", 60)),
            max_concurrent_requests=int(data.get("max_concurrent_requests", 10)),
            preferred_models=json.loads(data.get("preferred_models", "[]")),
            blocked_models=json.loads(data.get("blocked_models", "[]")),
            custom_routing_rules=json.loads(data.get("custom_routing_rules", "{}")),
            created_at=float(data.get("created_at", 0)),
            updated_at=float(data.get("updated_at", 0)),
            owner=data.get("owner", ""),
            description=data.get("description", ""),
            active=data.get("active", "True") == "True",
        )


class TenantManager:
    """
    Manages tenant policies with Redis-backed storage.

    Redis keys: freerelay:tenant:{namespace}
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def create_tenant(self, policy: TenantPolicy) -> str:
        """
        Create a new tenant policy.

        Validates the policy before persisting.
        Returns the namespace.
        """
        errors = self.validate_policy(policy)
        if errors:
            raise ValueError(f"Invalid tenant policy: {'; '.join(errors)}")

        policy.created_at = time.time()
        policy.updated_at = time.time()

        try:
            # Check for duplicate
            existing = await self._redis.exists(policy.key)
            if existing:
                raise ValueError(f"Tenant '{policy.namespace}' already exists")

            await self._redis.hset(policy.key, mapping=policy.to_dict())
            logger.info("tenant_created namespace=%s", policy.namespace)
            return policy.namespace

        except ValueError:
            raise
        except Exception:
            logger.exception("create_tenant_error namespace=%s", policy.namespace)
            raise

    async def get_tenant(self, namespace: str) -> TenantPolicy | None:
        """Retrieve a tenant policy by namespace."""
        key = f"{TENANT_KEY_PREFIX}:{namespace}"
        try:
            data = await self._redis.hgetall(key)
            if not data:
                return None
            return TenantPolicy.from_redis(data)
        except Exception:
            logger.exception("get_tenant_error namespace=%s", namespace)
            return None

    async def update_tenant(self, namespace: str, updates: dict[str, Any]) -> bool:
        """
        Update specific fields of a tenant policy.
        Validates the update before persisting.
        """
        existing = await self.get_tenant(namespace)
        if existing is None:
            raise ValueError(f"Tenant '{namespace}' not found")

        # Apply updates
        for field_name, value in updates.items():
            if hasattr(existing, field_name):
                setattr(existing, field_name, value)

        errors = self.validate_policy(existing)
        if errors:
            raise ValueError(f"Invalid update: {'; '.join(errors)}")

        existing.updated_at = time.time()

        try:
            await self._redis.hset(existing.key, mapping=existing.to_dict())
            logger.info(
                "tenant_updated namespace=%s fields=%s", namespace, list(updates.keys())
            )
            return True
        except Exception:
            logger.exception("update_tenant_error namespace=%s", namespace)
            return False

    async def delete_tenant(self, namespace: str) -> bool:
        """Delete a tenant policy."""
        key = f"{TENANT_KEY_PREFIX}:{namespace}"
        try:
            deleted = await self._redis.delete(key)
            if deleted:
                logger.info("tenant_deleted namespace=%s", namespace)
            return bool(deleted)
        except Exception:
            logger.exception("delete_tenant_error namespace=%s", namespace)
            return False

    async def list_tenants(self, active_only: bool = False) -> list[TenantPolicy]:
        """List all tenant policies."""
        try:
            tenants: list[TenantPolicy] = []
            async for key in self._redis.scan_iter(
                match=f"{TENANT_KEY_PREFIX}:*", count=200
            ):
                data = await self._redis.hgetall(key)
                if data:
                    tenant = TenantPolicy.from_redis(data)
                    if not active_only or tenant.active:
                        tenants.append(tenant)
            return sorted(tenants, key=lambda t: t.namespace)
        except Exception:
            logger.exception("list_tenants_error")
            return []

    async def create_default_tenant(
        self, namespace: str, owner: str = ""
    ) -> TenantPolicy:
        """Create a tenant with default settings."""
        policy = TenantPolicy(
            namespace=namespace,
            owner=owner,
            description=f"Default policy for {namespace}",
        )
        await self.create_tenant(policy)
        return policy

    def validate_policy(self, policy: TenantPolicy) -> list[str]:
        """
        Validate a tenant policy against the DSL schema.
        Returns a list of error messages (empty if valid).
        """
        errors: list[str] = []

        if not policy.namespace:
            errors.append("namespace is required")

        # Validate providers
        invalid_providers = set(policy.allowed_providers) - VALID_PROVIDERS
        if invalid_providers:
            errors.append(f"Invalid providers: {invalid_providers}")

        if not policy.allowed_providers:
            errors.append("At least one provider must be allowed")

        # Validate safety tier
        if policy.min_safety_tier not in VALID_SAFETY_TIERS:
            errors.append(f"Invalid safety tier: {policy.min_safety_tier}")

        # Validate economic policy
        if policy.economic_policy not in VALID_ECONOMIC_POLICIES:
            errors.append(f"Invalid economic policy: {policy.economic_policy}")

        # Validate cost ceiling
        if policy.cost_ceiling < 0:
            errors.append("cost_ceiling must be non-negative")

        # Validate rate limits
        if policy.rate_limit_rpm < 1:
            errors.append("rate_limit_rpm must be at least 1")

        if policy.max_concurrent_requests < 1:
            errors.append("max_concurrent_requests must be at least 1")

        # Validate models don't overlap
        overlap = set(policy.preferred_models) & set(policy.blocked_models)
        if overlap:
            errors.append(f"Models cannot be both preferred and blocked: {overlap}")

        return errors

    async def get_tenant_effective_policy(self, namespace: str) -> dict[str, Any]:
        """
        Compute the effective routing policy for a tenant,
        combining tenant settings with global defaults.
        """
        tenant = await self.get_tenant(namespace)
        if tenant is None:
            return {"error": "tenant_not_found"}

        return {
            "namespace": tenant.namespace,
            "allowed_providers": tenant.allowed_providers,
            "preferred_models": tenant.preferred_models,
            "blocked_models": tenant.blocked_models,
            "economic_policy": tenant.economic_policy,
            "min_safety_tier": tenant.min_safety_tier,
            "cost_ceiling": tenant.cost_ceiling,
            "rate_limit_rpm": tenant.rate_limit_rpm,
            "max_concurrent_requests": tenant.max_concurrent_requests,
            "pii_masking": tenant.pii_masking,
            "audit_trail": tenant.audit_trail,
            "custom_routing_rules": tenant.custom_routing_rules,
        }
