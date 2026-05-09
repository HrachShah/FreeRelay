"""
FreeRelay — Shadow Router
============================
Fires async shadow requests to a secondary provider after the primary response.
Compares responses without affecting the user-facing result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

SHADOW_RESULTS_KEY = "freerelay:experiment:shadow"
SHADOW_CONCURRENCY_LIMIT = 10


@dataclass
class ShadowResult:
    """Result of a shadow comparison between primary and shadow providers."""

    request_id: str
    experiment_id: str
    primary_provider: str
    primary_model: str
    shadow_provider: str
    shadow_model: str
    primary_output: str
    shadow_output: str
    similarity_score: float
    primary_latency_ms: float
    shadow_latency_ms: float
    latency_ratio: float  # shadow / primary
    timestamp: float = field(default_factory=time.time)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "experiment_id": self.experiment_id,
            "primary_provider": self.primary_provider,
            "primary_model": self.primary_model,
            "shadow_provider": self.shadow_provider,
            "shadow_model": self.shadow_model,
            "primary_output": self.primary_output[:500],  # truncate for storage
            "shadow_output": self.shadow_output[:500],
            "similarity_score": self.similarity_score,
            "primary_latency_ms": self.primary_latency_ms,
            "shadow_latency_ms": self.shadow_latency_ms,
            "latency_ratio": self.latency_ratio,
            "timestamp": self.timestamp,
            "error": self.error,
        }


class ShadowRouter:
    """
    Fires shadow requests to a secondary provider and compares results.

    Shadow requests are dispatched asynchronously after the primary response
    is returned. They never affect the user-facing response.

    Uses a semaphore to limit concurrent shadow requests and avoid
    overwhelming provider rate limits.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        provider_caller: Any | None = None,
    ) -> None:
        self._redis = redis_client
        self._provider_caller = provider_caller
        self._semaphore = asyncio.Semaphore(SHADOW_CONCURRENCY_LIMIT)
        self._active_shadows: int = 0

    async def fire_shadow_request(
        self,
        request_id: str,
        experiment_id: str,
        primary_provider: str,
        primary_model: str,
        primary_output: str,
        primary_latency_ms: float,
        shadow_provider: str,
        shadow_model: str,
        prompt: str,
        timeout_s: float = 30.0,
    ) -> ShadowResult:
        """
        Fire a shadow request to the secondary provider.

        Args:
            request_id: Original request ID.
            experiment_id: Experiment this shadow belongs to.
            primary_provider: Provider used for the real response.
            primary_model: Model used for the real response.
            primary_output: The real response text.
            primary_latency_ms: Latency of the primary response.
            shadow_provider: Provider to use for shadow.
            shadow_model: Model to use for shadow.
            prompt: The original user prompt.
            timeout_s: Timeout for the shadow request.

        Returns:
            ShadowResult with comparison data.
        """
        self._active_shadows += 1
        try:
            async with self._semaphore:
                return await self._execute_shadow(
                    request_id=request_id,
                    experiment_id=experiment_id,
                    primary_provider=primary_provider,
                    primary_model=primary_model,
                    primary_output=primary_output,
                    primary_latency_ms=primary_latency_ms,
                    shadow_provider=shadow_provider,
                    shadow_model=shadow_model,
                    prompt=prompt,
                    timeout_s=timeout_s,
                )
        finally:
            self._active_shadows -= 1

    async def _execute_shadow(
        self,
        request_id: str,
        experiment_id: str,
        primary_provider: str,
        primary_model: str,
        primary_output: str,
        primary_latency_ms: float,
        shadow_provider: str,
        shadow_model: str,
        prompt: str,
        timeout_s: float,
    ) -> ShadowResult:
        """Execute the shadow request and compare with primary."""
        shadow_output = ""
        shadow_latency_ms = 0.0
        error = None

        start = time.monotonic()
        try:
            if self._provider_caller:
                result = await asyncio.wait_for(
                    self._provider_caller(
                        provider=shadow_provider,
                        model=shadow_model,
                        prompt=prompt,
                        timeout=timeout_s,
                    ),
                    timeout=timeout_s + 5,
                )
                shadow_output = result.get("output", "")
                shadow_latency_ms = result.get("ttft_ms", 0.0) + result.get(
                    "total_ms", 0.0
                )
            else:
                # Placeholder when no caller configured
                shadow_output = (
                    f"[shadow placeholder from {shadow_provider}/{shadow_model}]"
                )
                shadow_latency_ms = (time.monotonic() - start) * 1000

        except TimeoutError:
            error = f"Shadow timeout after {timeout_s}s"
            shadow_latency_ms = timeout_s * 1000
        except Exception as exc:
            error = f"Shadow error: {exc}"
            shadow_latency_ms = (time.monotonic() - start) * 1000

        # Compare responses
        similarity = compare_responses(primary_output, shadow_output)
        latency_ratio = shadow_latency_ms / max(primary_latency_ms, 1.0)

        result = ShadowResult(
            request_id=request_id,
            experiment_id=experiment_id,
            primary_provider=primary_provider,
            primary_model=primary_model,
            shadow_provider=shadow_provider,
            shadow_model=shadow_model,
            primary_output=primary_output,
            shadow_output=shadow_output,
            similarity_score=similarity,
            primary_latency_ms=primary_latency_ms,
            shadow_latency_ms=shadow_latency_ms,
            latency_ratio=latency_ratio,
            error=error,
        )

        # Store result
        await self._store_shadow_result(result)

        logger.debug(
            "shadow_complete request=%s similarity=%.3f latency_ratio=%.2f error=%s",
            request_id,
            similarity,
            latency_ratio,
            error,
        )

        return result

    async def _store_shadow_result(self, result: ShadowResult) -> None:
        """Store shadow comparison result in Redis."""
        try:
            key = f"{SHADOW_RESULTS_KEY}:{result.experiment_id}"
            data = json.dumps(result.to_dict())
            pipe = self._redis.pipeline()
            pipe.lpush(key, data)
            pipe.ltrim(key, 0, 999)  # keep last 1000 shadow results
            await pipe.execute()
        except (TypeError, ValueError, OSError):
            logger.exception("store_shadow_result_error")

    async def get_shadow_results(
        self,
        experiment_id: str,
        count: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent shadow comparison results."""
        try:
            key = f"{SHADOW_RESULTS_KEY}:{experiment_id}"
            raw = await self._redis.lrange(key, 0, count - 1)
            return [json.loads(r) for r in raw]
        except (ValueError, OSError):
            logger.exception("get_shadow_results_error")
            return []

    async def get_shadow_summary(self, experiment_id: str) -> dict[str, Any]:
        """Aggregate shadow results into a summary."""
        results = await self.get_shadow_results(experiment_id, count=500)
        if not results:
            return {"total_shadows": 0}

        similarities = [
            r["similarity_score"]
            for r in results
            if r.get("similarity_score") is not None
        ]
        latency_ratios = [
            r["latency_ratio"] for r in results if r.get("latency_ratio") is not None
        ]
        errors = [r for r in results if r.get("error")]

        return {
            "total_shadows": len(results),
            "mean_similarity": sum(similarities) / max(len(similarities), 1),
            "min_similarity": min(similarities) if similarities else 0,
            "max_similarity": max(similarities) if similarities else 0,
            "mean_latency_ratio": sum(latency_ratios) / max(len(latency_ratios), 1),
            "error_count": len(errors),
            "error_rate": len(errors) / max(len(results), 1),
        }

    @property
    def active_shadow_count(self) -> int:
        return self._active_shadows


def compare_responses(primary: str, shadow: str) -> float:
    """
    Compare two response strings for similarity.

    Uses SequenceMatcher for token-level similarity.
    Returns a score between 0.0 (completely different) and 1.0 (identical).
    """
    if not primary and not shadow:
        return 1.0
    if not primary or not shadow:
        return 0.0

    # Normalize whitespace
    p_norm = " ".join(primary.lower().split())
    s_norm = " ".join(shadow.lower().split())

    return SequenceMatcher(None, p_norm, s_norm).ratio()
