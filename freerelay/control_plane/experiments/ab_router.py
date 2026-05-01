"""
FreeRelay — A/B Router & Experiment Manager
==============================================
Manages A/B routing, canary deployments, and experiment lifecycle.
Supports hash-based assignment, metrics aggregation, and auto-rollback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

EXPERIMENT_KEY_PREFIX = "freerelay:experiment"
METRICS_KEY_PREFIX = "freerelay:experiment:metrics"

# Auto-rollback thresholds for canary deployments
CANARY_QUALITY_THRESHOLD = 0.4  # rollback if mean quality drops below
CANARY_MIN_SAMPLES = 20  # minimum samples before rollback check


class ExperimentType(StrEnum):
    """Types of experiments supported."""

    AB_ROUTING = "ab_routing"
    CANARY = "canary"
    SHADOW = "shadow"
    REPLAY = "replay"
    WHAT_IF = "what_if"


@dataclass
class ExperimentConfig:
    """Configuration for a single experiment."""

    id: str
    type: ExperimentType
    name: str
    description: str = ""
    policy_a: dict[str, Any] = field(default_factory=dict)
    policy_b: dict[str, Any] = field(default_factory=dict)
    split_percentage: int = 50  # 0-100, percentage for arm B
    metrics: list[str] = field(
        default_factory=lambda: ["quality", "latency_ms", "cost"]
    )
    quality_threshold: float = CANARY_QUALITY_THRESHOLD
    auto_rollback: bool = True
    active: bool = False
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    stopped_at: float = 0.0
    owner: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "policy_a": json.dumps(self.policy_a),
            "policy_b": json.dumps(self.policy_b),
            "split_percentage": str(self.split_percentage),
            "metrics": json.dumps(self.metrics),
            "quality_threshold": str(self.quality_threshold),
            "auto_rollback": str(self.auto_rollback),
            "active": str(self.active),
            "created_at": str(self.created_at),
            "started_at": str(self.started_at),
            "stopped_at": str(self.stopped_at),
            "owner": self.owner,
            "tags": json.dumps(self.tags),
        }

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> ExperimentConfig:
        """Hydrate from Redis hash."""
        return cls(
            id=data.get("id", ""),
            type=ExperimentType(data.get("type", "ab_routing")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            policy_a=json.loads(data.get("policy_a", "{}")),
            policy_b=json.loads(data.get("policy_b", "{}")),
            split_percentage=int(data.get("split_percentage", 50)),
            metrics=json.loads(data.get("metrics", '["quality","latency_ms","cost"]')),
            quality_threshold=float(
                data.get("quality_threshold", CANARY_QUALITY_THRESHOLD)
            ),
            auto_rollback=data.get("auto_rollback", "True") == "True",
            active=data.get("active", "False") == "True",
            created_at=float(data.get("created_at", 0)),
            started_at=float(data.get("started_at", 0)),
            stopped_at=float(data.get("stopped_at", 0)),
            owner=data.get("owner", ""),
            tags=json.loads(data.get("tags", "[]")),
        )


@dataclass
class ArmMetrics:
    """Aggregated metrics for one arm of an experiment."""

    total_requests: int = 0
    success_count: int = 0
    total_quality: float = 0.0
    total_latency_ms: float = 0.0
    total_cost: float = 0.0

    @property
    def mean_quality(self) -> float:
        return self.total_quality / max(self.total_requests, 1)

    @property
    def mean_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.total_requests, 1)

    @property
    def mean_cost(self) -> float:
        return self.total_cost / max(self.total_requests, 1)

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_requests, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "mean_quality": self.mean_quality,
            "mean_latency_ms": self.mean_latency_ms,
            "mean_cost": self.mean_cost,
            "success_rate": self.success_rate,
        }


def hash_based_assignment(request_id: str, experiment_id: str, split: int = 50) -> str:
    """
    Deterministic hash-based experiment arm assignment.
    Always returns the same arm for the same request_id + experiment_id.

    Returns 'A' or 'B'.
    """
    combined = f"{request_id}:{experiment_id}"
    hash_digest = hashlib.sha256(combined.encode()).hexdigest()
    bucket = int(hash_digest[:8], 16) % 100
    return "B" if bucket < split else "A"


class ExperimentManager:
    """
    Manages experiment lifecycle, assignment, and metrics.

    Redis keys:
    - freerelay:experiment:{id} — config hash
    - freerelay:experiment:metrics:{id}:A — arm A metrics
    - freerelay:experiment:metrics:{id}:B — arm B metrics
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def create_experiment(self, config: ExperimentConfig) -> str:
        """
        Create a new experiment. Returns the experiment ID.
        """
        if not config.id:
            config.id = str(uuid.uuid4())[:8]

        key = f"{EXPERIMENT_KEY_PREFIX}:{config.id}"
        try:
            await self._redis.hset(key, mapping=config.to_dict())
            # Initialize metric counters
            for arm in ("A", "B"):
                m_key = f"{METRICS_KEY_PREFIX}:{config.id}:{arm}"
                await self._redis.hset(m_key, mapping=ArmMetrics().to_dict())
            logger.info(
                "experiment_created id=%s type=%s name=%s",
                config.id,
                config.type.value,
                config.name,
            )
            return config.id
        except Exception as exc:
            logger.exception("create_experiment_error: %s", exc)
            raise

    async def start_experiment(self, experiment_id: str) -> bool:
        """Activate an experiment."""
        key = f"{EXPERIMENT_KEY_PREFIX}:{experiment_id}"
        try:
            data = await self._redis.hgetall(key)
            if not data:
                logger.error("experiment_not_found id=%s", experiment_id)
                return False
            await self._redis.hset(
                key,
                mapping={
                    "active": "True",
                    "started_at": str(time.time()),
                },
            )
            logger.info("experiment_started id=%s", experiment_id)
            return True
        except Exception as exc:
            logger.exception("start_experiment_error: %s", exc)
            return False

    async def stop_experiment(self, experiment_id: str, reason: str = "manual") -> bool:
        """Deactivate an experiment."""
        key = f"{EXPERIMENT_KEY_PREFIX}:{experiment_id}"
        try:
            await self._redis.hset(
                key,
                mapping={
                    "active": "False",
                    "stopped_at": str(time.time()),
                    "stop_reason": reason,
                },
            )
            logger.info("experiment_stopped id=%s reason=%s", experiment_id, reason)
            return True
        except Exception as exc:
            logger.exception("stop_experiment_error: %s", exc)
            return False

    async def get_experiment(self, experiment_id: str) -> ExperimentConfig | None:
        """Get experiment configuration."""
        key = f"{EXPERIMENT_KEY_PREFIX}:{experiment_id}"
        try:
            data = await self._redis.hgetall(key)
            if not data:
                return None
            return ExperimentConfig.from_redis(data)
        except Exception as exc:
            logger.exception("get_experiment_error: %s", exc)
            return None

    async def list_experiments(
        self, active_only: bool = False
    ) -> list[ExperimentConfig]:
        """List all experiments."""
        try:
            experiments: list[ExperimentConfig] = []
            async for key in self._redis.scan_iter(
                match=f"{EXPERIMENT_KEY_PREFIX}:*", count=200
            ):
                # Skip metrics keys
                if ":metrics:" in key:
                    continue
                data = await self._redis.hgetall(key)
                if data:
                    config = ExperimentConfig.from_redis(data)
                    if not active_only or config.active:
                        experiments.append(config)
            return experiments
        except Exception as exc:
            logger.exception("list_experiments_error: %s", exc)
            return []

    async def assign_arm(self, request_id: str, experiment_id: str) -> str | None:
        """
        Assign a request to an experiment arm.
        Returns 'A', 'B', or None if experiment not active.
        """
        config = await self.get_experiment(experiment_id)
        if not config or not config.active:
            return None

        return hash_based_assignment(request_id, experiment_id, config.split_percentage)

    async def record_outcome(
        self,
        experiment_id: str,
        arm: str,
        quality: float,
        latency_ms: float,
        cost: float,
        success: bool,
    ) -> None:
        """Record a single outcome for an experiment arm."""
        m_key = f"{METRICS_KEY_PREFIX}:{experiment_id}:{arm}"
        try:
            # Use HINCRBY for integer counters, HSET for floats
            pipe = self._redis.pipeline()
            pipe.hincrby(m_key, "total_requests", 1)
            if success:
                pipe.hincrby(m_key, "success_count", 1)

            # For floats, read-modify-write
            data = await self._redis.hgetall(m_key)
            total_requests = int(data.get("total_requests", 0)) + 1
            total_quality = float(data.get("total_quality", 0)) + quality
            total_latency = float(data.get("total_latency_ms", 0)) + latency_ms
            total_cost = float(data.get("total_cost", 0)) + cost

            await self._redis.hset(
                m_key,
                mapping={
                    "total_quality": str(total_quality),
                    "total_latency_ms": str(total_latency),
                    "total_cost": str(total_cost),
                },
            )

            # Check canary auto-rollback
            config = await self.get_experiment(experiment_id)
            if (
                config
                and config.type == ExperimentType.CANARY
                and config.auto_rollback
                and arm == "B"
            ):
                if total_requests >= CANARY_MIN_SAMPLES:
                    mean_q = total_quality / total_requests
                    if mean_q < config.quality_threshold:
                        await self.stop_experiment(
                            experiment_id,
                            reason=f"auto_rollback: quality {mean_q:.3f} < {config.quality_threshold}",
                        )
                        logger.warning(
                            "canary_auto_rollback id=%s quality=%.3f threshold=%.3f",
                            experiment_id,
                            mean_q,
                            config.quality_threshold,
                        )

        except Exception as exc:
            logger.error(
                "record_outcome_error experiment=%s arm=%s: %s",
                experiment_id,
                arm,
                exc,
            )

    async def get_arm_metrics(self, experiment_id: str, arm: str) -> ArmMetrics:
        """Get current metrics for an experiment arm."""
        m_key = f"{METRICS_KEY_PREFIX}:{experiment_id}:{arm}"
        try:
            data = await self._redis.hgetall(m_key)
            if not data:
                return ArmMetrics()
            return ArmMetrics(
                total_requests=int(data.get("total_requests", 0)),
                success_count=int(data.get("success_count", 0)),
                total_quality=float(data.get("total_quality", 0)),
                total_latency_ms=float(data.get("total_latency_ms", 0)),
                total_cost=float(data.get("total_cost", 0)),
            )
        except Exception as exc:
            logger.exception("get_arm_metrics_error: %s", exc)
            return ArmMetrics()

    async def get_experiment_status(self, experiment_id: str) -> dict[str, Any]:
        """Get full experiment status including both arm metrics."""
        config = await self.get_experiment(experiment_id)
        if not config:
            return {"error": "experiment_not_found"}

        metrics_a = await self.get_arm_metrics(experiment_id, "A")
        metrics_b = await self.get_arm_metrics(experiment_id, "B")

        return {
            "config": {
                "id": config.id,
                "name": config.name,
                "type": config.type.value,
                "active": config.active,
                "split_percentage": config.split_percentage,
                "quality_threshold": config.quality_threshold,
                "auto_rollback": config.auto_rollback,
                "created_at": config.created_at,
                "started_at": config.started_at,
                "stopped_at": config.stopped_at,
            },
            "arm_a": metrics_a.to_dict(),
            "arm_b": metrics_b.to_dict(),
            "winner": self._determine_winner(metrics_a, metrics_b),
        }

    def _determine_winner(self, a: ArmMetrics, b: ArmMetrics) -> str | None:
        """Simple winner determination by mean quality."""
        if a.total_requests < 10 or b.total_requests < 10:
            return None  # insufficient data
        if a.mean_quality > b.mean_quality + 0.02:
            return "A"
        if b.mean_quality > a.mean_quality + 0.02:
            return "B"
        return "tie"

    async def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment and its metrics."""
        try:
            keys_to_delete = [
                f"{EXPERIMENT_KEY_PREFIX}:{experiment_id}",
                f"{METRICS_KEY_PREFIX}:{experiment_id}:A",
                f"{METRICS_KEY_PREFIX}:{experiment_id}:B",
            ]
            deleted = await self._redis.delete(*keys_to_delete)
            logger.info("experiment_deleted id=%s", experiment_id)
            return deleted > 0
        except Exception as exc:
            logger.exception("delete_experiment_error: %s", exc)
            return False
