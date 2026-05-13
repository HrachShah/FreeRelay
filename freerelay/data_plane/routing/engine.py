"""
FreeRelay Data Plane — Routing Engine (§5)
=============================================
Expected utility scoring, policy DSL, UCB exploration.
Selects optimal provider/model for each request.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis
from freerelay.data_plane.profiler.workload import WorkloadProfile

logger = logging.getLogger("freerelay.data_plane.routing")


@dataclass
class ModelSlot:
    """A provider+model combination available for routing."""

    provider: str
    model: str
    latency_p95_ms: float = 1000.0
    schema_compliance_rate: float = 0.95
    cost_per_1k_tokens: float = 0.001
    quality_tier: str = "medium"
    speed_tier: str = "medium"
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_json_mode: bool = False
    circuit_score: float = 1.0  # 1.0=closed, 0.5=half_open, 0.0=open


@dataclass
class ProviderScore:
    """Scored provider candidate."""

    provider: str
    model: str
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class RoutingDecision:
    """Full routing decision with all scored candidates."""

    selected_provider: str
    selected_model: str
    scores: list[ProviderScore] = field(default_factory=list)
    policy_applied: str = ""
    latency_ms: float = 0.0


class RoutingEngine:
    """
    Routing engine that selects optimal provider/model using expected utility.

    Capabilities:
      - select(): single best provider
      - select_top_n(): top N providers
      - select_cheapest(): cheapest viable provider
      - select_strongest(): highest quality provider
      - select_diverse(): maximize provider diversity
      - select_for_repair(): highest schema compliance
    """

    def __init__(self, redis: Any | None = None) -> None:
        self._redis = redis
        self._capability_cache: dict[str, dict[str, Any]] = {}

    async def _load_capabilities(self, provider: str, model: str) -> dict[str, Any]:
        """Load capability record from Redis or cache."""
        key = f"{provider}/{model}"
        if key in self._capability_cache:
            return self._capability_cache[key]

        if self._redis is not None:
            try:
                data = await self._redis.hgetall(f"freerelay:capabilities:{key}")
                if data:
                    caps = {
                        k.decode() if isinstance(k, bytes) else k: v
                        for k, v in data.items()
                    }
                    self._capability_cache[key] = caps
                    return caps
            except (redis.ResponseError, redis.ConnectionError, OSError):
                logger.debug("Failed to load capabilities for %s", key)

        return {}

    def select(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
        constraints: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        """
        Select the single best provider/model.

        Args:
            profile: Workload profile from the profiler.
            model_pool: Available provider/model slots.
            constraints: Optional constraints (e.g., min_quality, max_cost).

        Returns:
            RoutingDecision with the best provider and full score list.
        """
        start = time.monotonic()
        scored = self._score_all(profile, model_pool, constraints)

        if not scored:
            return RoutingDecision(
                selected_provider="",
                selected_model="",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        best = scored[0]
        return RoutingDecision(
            selected_provider=best.provider,
            selected_model=best.model,
            scores=scored,
            latency_ms=(time.monotonic() - start) * 1000,
        )

    def select_top_n(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
        n: int = 3,
        constraints: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        """
        Select the top N provider/model pairs.

        Returns:
            List of (provider, model) tuples sorted by score descending.
        """
        scored = self._score_all(profile, model_pool, constraints)
        return [(s.provider, s.model) for s in scored[:n]]

    def select_cheapest(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
    ) -> tuple[str, str]:
        """
        Select the cheapest viable provider.

        Returns:
            (provider, model) tuple.
        """
        scored = self._score_all(profile, model_pool)
        if not scored:
            return ("", "")

        # Re-sort by cost (ascending) among viable options
        viable = [s for s in scored if s.score > 0.1]
        if not viable:
            viable = scored

        cheapest = min(
            viable,
            key=lambda s: self._get_cost(s.provider, s.model, model_pool),
        )
        return (cheapest.provider, cheapest.model)

    def select_strongest(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
    ) -> tuple[str, str]:
        """
        Select the highest quality provider.

        Returns:
            (provider, model) tuple.
        """
        scored = self._score_all(profile, model_pool)
        if not scored:
            return ("", "")

        # Re-sort by quality tier
        quality_order = {"high": 3, "medium": 2, "low": 1}
        strongest = max(
            scored,
            key=lambda s: quality_order.get(
                self._get_quality(s.provider, s.model, model_pool), 0
            ),
        )
        return (strongest.provider, strongest.model)

    def select_diverse(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
        n: int = 3,
    ) -> list[tuple[str, str]]:
        """
        Select N providers maximizing diversity (different providers preferred).

        Returns:
            List of (provider, model) tuples.
        """
        scored = self._score_all(profile, model_pool)
        selected: list[tuple[str, str]] = []
        used_providers: set[str] = set()

        # First pass: one per provider
        for s in scored:
            if s.provider not in used_providers and len(selected) < n:
                selected.append((s.provider, s.model))
                used_providers.add(s.provider)

        # Second pass: fill remaining slots with best scores
        for s in scored:
            if (s.provider, s.model) not in selected and len(selected) < n:
                selected.append((s.provider, s.model))

        return selected

    def select_for_repair(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
    ) -> tuple[str, str]:
        """
        Select the provider with highest schema compliance rate.

        Returns:
            (provider, model) tuple.
        """
        if not model_pool:
            return ("", "")

        best = max(model_pool, key=lambda m: m.schema_compliance_rate)
        return (best.provider, best.model)

    def _score_all(
        self,
        profile: WorkloadProfile,
        model_pool: list[ModelSlot],
        constraints: dict[str, Any] | None = None,
    ) -> list[ProviderScore]:
        """Score all providers and return sorted list."""
        from freerelay.data_plane.routing.scorer import expected_utility

        scored: list[ProviderScore] = []
        for slot in model_pool:
            if constraints:
                if not self._meets_constraints(slot, constraints):
                    continue

            score, breakdown = expected_utility(
                slot=slot,
                profile=profile,
            )
            scored.append(
                ProviderScore(
                    provider=slot.provider,
                    model=slot.model,
                    score=score,
                    breakdown=breakdown,
                )
            )

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored

    def _meets_constraints(
        self,
        slot: ModelSlot,
        constraints: dict[str, Any],
    ) -> bool:
        """Check if a slot meets the given constraints."""
        if "min_quality" in constraints:
            quality_order = {"low": 1, "medium": 2, "high": 3}
            min_q = quality_order.get(constraints["min_quality"], 0)
            slot_q = quality_order.get(slot.quality_tier, 0)
            if slot_q < min_q:
                return False

        if "max_cost" in constraints:
            if slot.cost_per_1k_tokens > constraints["max_cost"]:
                return False

        if "require_tools" in constraints and constraints["require_tools"]:
            if not slot.supports_tools:
                return False

        if "require_json" in constraints and constraints["require_json"]:
            if not slot.supports_json_mode:
                return False

        if "require_streaming" in constraints and constraints["require_streaming"]:
            if not slot.supports_streaming:
                return False

        return True

    def _get_cost(self, provider: str, model: str, pool: list[ModelSlot]) -> float:
        for slot in pool:
            if slot.provider == provider and slot.model == model:
                return slot.cost_per_1k_tokens
        return float("inf")

    def _get_quality(self, provider: str, model: str, pool: list[ModelSlot]) -> str:
        for slot in pool:
            if slot.provider == provider and slot.model == model:
                return slot.quality_tier
        return "low"
