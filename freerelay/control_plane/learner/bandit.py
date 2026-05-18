"""
FreeRelay — UCB Bandit Implementation
=======================================
Upper Confidence Bound multi-armed bandit for provider/model selection.
Redis-backed state with Welford's online variance algorithm and EWMA quality tracking.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

BANDIT_KEY_PREFIX = "freerelay:bandit"

# Quality signal weights
W_OUTPUT_VALID = 0.4
W_JUDGE_SCORE = 0.3
W_NO_REPAIR = 0.15
W_NO_RETRY = 0.1
W_NO_REGENERATE = 0.05

# EWMA alpha schedule
ALPHA_FRESH = 0.3  # used when n_pulls <= threshold
ALPHA_MATURE = 0.1  # used when n_pulls > threshold
EWMA_PULL_THRESHOLD = 100

# UCB exploration constant
UCB_C = 2.0

# Prior defaults
DEFAULT_MEAN_QUALITY = 0.5
DEFAULT_EWMA_QUALITY = 0.5
PRIOR_N_PULLS = 0


@dataclass
class BanditArm:
    """State for a single bandit arm (provider + model + task_family)."""

    provider: str
    model: str
    task_family: str
    mean_quality: float = DEFAULT_MEAN_QUALITY
    n_pulls: int = PRIOR_N_PULLS
    sum_quality: float = 0.0
    ewma_quality: float = DEFAULT_EWMA_QUALITY
    variance: float = 0.0
    m2: float = 0.0  # sum of squared deviations (Welford)
    last_updated_ts: float = field(default_factory=time.time)

    @property
    def key(self) -> str:
        """Redis key for this arm."""
        return f"{BANDIT_KEY_PREFIX}:{self.provider}:{self.model}:{self.task_family}"

    def ucb_score(self, total_pulls: int) -> float:
        """Compute UCB1 score given total pulls across all arms."""
        if self.n_pulls == 0:
            return float("inf")  # guarantee exploration
        exploration_bonus = UCB_C * math.sqrt(
            math.log(max(total_pulls, 1)) / self.n_pulls
        )
        return self.ewma_quality + exploration_bonus

    @classmethod
    def from_redis(
        cls, provider: str, model: str, task_family: str, data: dict[str, str]
    ) -> BanditArm:
        """Hydrate an arm from Redis hash data."""

        def _float(val: str | None, default: float) -> float:
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        def _int(val: str | None, default: int) -> int:
            try:
                return int(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        return cls(
            provider=provider,
            model=model,
            task_family=task_family,
            mean_quality=_float(data.get("mean_quality"), DEFAULT_MEAN_QUALITY),
            n_pulls=_int(data.get("n_pulls"), PRIOR_N_PULLS),
            sum_quality=_float(data.get("sum_quality"), 0.0),
            ewma_quality=_float(data.get("ewma_quality"), DEFAULT_EWMA_QUALITY),
            variance=_float(data.get("variance"), 0.0),
            m2=_float(data.get("m2"), 0.0),
            last_updated_ts=_float(data.get("last_updated_ts"), time.time()),
        )

    def to_redis(self) -> dict[str, str]:
        """Serialize arm state to Redis hash fields."""
        return {
            "mean_quality": str(self.mean_quality),
            "n_pulls": str(self.n_pulls),
            "sum_quality": str(self.sum_quality),
            "ewma_quality": str(self.ewma_quality),
            "variance": str(self.variance),
            "m2": str(self.m2),
            "last_updated_ts": str(self.last_updated_ts),
        }


@dataclass
class OutcomeFields:
    """Parsed outcome fields used for quality signal computation."""

    output_valid: float = 0.0
    judge_score: float = 0.5
    repair_triggered: float = 0.0
    client_retried: float = 0.0
    client_regenerated: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutcomeFields:
        """Parse from outcome record dict."""
        return cls(
            output_valid=float(data.get("output_valid", 0)),
            judge_score=float(data.get("judge_score", 0.5)),
            repair_triggered=float(data.get("repair_triggered", 0)),
            client_retried=float(data.get("client_retried", 0)),
            client_regenerated=float(data.get("client_regenerated", 0)),
        )


def compute_quality_signal(outcome: OutcomeFields) -> float:
    """
    Compute weighted quality signal from outcome fields.

    Signal = 0.4 * output_valid
           + 0.3 * judge_score
           + 0.15 * (1 - repair_triggered)
           + 0.1 * (1 - client_retried)
           + 0.05 * (1 - client_regenerated)
    """
    signal = (
        W_OUTPUT_VALID * outcome.output_valid
        + W_JUDGE_SCORE * outcome.judge_score
        + W_NO_REPAIR * (1.0 - outcome.repair_triggered)
        + W_NO_RETRY * (1.0 - outcome.client_retried)
        + W_NO_REGENERATE * (1.0 - outcome.client_regenerated)
    )
    return max(0.0, min(1.0, signal))


def update_arm_welford(arm: BanditArm, quality_signal: float) -> BanditArm:
    """
    Update bandit arm using Welford's online algorithm for variance + EWMA.

    Returns a new BanditArm with updated statistics.
    """
    now = time.time()
    n = arm.n_pulls + 1

    # Welford's online mean + variance
    delta = quality_signal - arm.mean_quality
    new_mean = arm.mean_quality + delta / n
    delta2 = quality_signal - new_mean
    new_m2 = arm.m2 + delta * delta2
    new_variance = new_m2 / n if n > 1 else 0.0

    # EWMA update
    alpha = ALPHA_FRESH if n <= EWMA_PULL_THRESHOLD else ALPHA_MATURE
    new_ewma = alpha * quality_signal + (1 - alpha) * arm.ewma_quality

    return BanditArm(
        provider=arm.provider,
        model=arm.model,
        task_family=arm.task_family,
        mean_quality=new_mean,
        n_pulls=n,
        sum_quality=arm.sum_quality + quality_signal,
        ewma_quality=new_ewma,
        variance=new_variance,
        m2=new_m2,
        last_updated_ts=now,
    )


def estimate_judge_score(
    task_family: str,
    output_length: int,
    schema_present: bool,
) -> float:
    """
    Estimate judge score when the actual judge has not yet run.
    Uses heuristics based on task family and output characteristics.
    """
    base = 0.5

    # Longer outputs for code/summarization tend to be more complete
    if task_family in ("code_generation", "summarization"):
        if output_length > 500:
            base += 0.1
        elif output_length > 200:
            base += 0.05

    # Schema presence implies structured output capability
    if schema_present:
        base += 0.1

    # JSON-schema tasks are often more reliable
    if task_family == "json_schema":
        base += 0.05

    # Tool calls are binary; without judge we assume neutral
    if task_family == "tool_call":
        base = 0.5

    return max(0.0, min(1.0, base))


class BanditState:
    """
    Manages bandit arms per (provider, model, task_family) combination.
    Backed by Redis hashes at freerelay:bandit:{provider}:{model}:{family}.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get_arm(self, provider: str, model: str, task_family: str) -> BanditArm:
        """Load arm state from Redis, returning defaults if missing."""
        key = f"{BANDIT_KEY_PREFIX}:{provider}:{model}:{task_family}"
        data = await self._redis.hgetall(key)
        if not data:
            return BanditArm(provider=provider, model=model, task_family=task_family)
        return BanditArm.from_redis(provider, model, task_family, data)

    async def save_arm(self, arm: BanditArm) -> None:
        """Persist arm state to Redis."""
        await self._redis.hset(arm.key, mapping=arm.to_redis())

    async def update_arm(
        self,
        provider: str,
        model: str,
        task_family: str,
        outcome: OutcomeFields,
    ) -> BanditArm:
        """
        Full update pipeline: load arm → compute signal → Welford update → persist.
        Returns the updated arm.
        """
        arm = await self.get_arm(provider, model, task_family)
        quality_signal = compute_quality_signal(outcome)
        updated = update_arm_welford(arm, quality_signal)
        await self.save_arm(updated)
        logger.debug(
            "bandit_arm_updated provider=%s model=%s family=%s signal=%.4f ewma=%.4f pulls=%d",
            provider,
            model,
            task_family,
            quality_signal,
            updated.ewma_quality,
            updated.n_pulls,
        )
        return updated

    async def select_best_arm(
        self,
        arms: list[tuple[str, str, str]],
        task_family: str,
    ) -> tuple[str, str]:
        """
        Select the best (provider, model) using UCB1 over the given arms.
        Returns (provider, model) tuple.
        """
        loaded: list[BanditArm] = []
        for provider, model, fam in arms:
            arm = await self.get_arm(provider, model, fam if fam else task_family)
            loaded.append(arm)

        total_pulls = sum(a.n_pulls for a in loaded)
        if total_pulls == 0:
            total_pulls = len(loaded)  # avoid log(0)

        best = max(loaded, key=lambda a: a.ucb_score(total_pulls))
        return best.provider, best.model

    async def list_arms(self, provider: str | None = None) -> list[BanditArm]:
        """List all arms, optionally filtered by provider prefix."""
        pattern = f"{BANDIT_KEY_PREFIX}:"
        if provider:
            pattern += f"{provider}:"
        pattern += "*"

        keys = []
        async for key in self._redis.scan_iter(match=pattern, count=200):
            keys.append(key)

        arms: list[BanditArm] = []
        for key in keys:
            parts = key.split(":")
            if len(parts) >= 5:
                p, m, f = parts[2], parts[3], parts[4]
                data = await self._redis.hgetall(key)
                if data:
                    arms.append(BanditArm.from_redis(p, m, f, data))
        return arms

    async def reset_arm(self, provider: str, model: str, task_family: str) -> None:
        """Reset an arm to defaults (useful for experiments)."""
        key = f"{BANDIT_KEY_PREFIX}:{provider}:{model}:{task_family}"
        await self._redis.delete(key)
        logger.info(
            "bandit_arm_reset provider=%s model=%s family=%s",
            provider,
            model,
            task_family,
        )
