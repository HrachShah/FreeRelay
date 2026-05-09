"""
FreeRelay — What-If Simulator
================================
Simulates counterfactual scenarios: "What if we had used policy X
for all requests in time window T?"
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

from freerelay.control_plane.experiments.replay import (
    ReplayEngine,
    ReplayReport,
)

logger = logging.getLogger(__name__)

SIMULATION_RESULTS_KEY = "freerelay:experiment:simulation"


@dataclass
class SimulationScenario:
    """Configuration for a what-if simulation."""

    name: str
    policy: dict[str, Any]
    description: str = ""
    start_time: float | None = None
    end_time: float | None = None
    max_records: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "policy": json.dumps(self.policy),
            "description": self.description,
            "start_time": str(self.start_time) if self.start_time else "",
            "end_time": str(self.end_time) if self.end_time else "",
            "max_records": str(self.max_records),
        }


@dataclass
class SimulationResult:
    """Result of a what-if simulation with scenario comparison."""

    scenario: SimulationScenario
    report: ReplayReport
    baseline_quality: float
    scenario_quality: float
    quality_delta: float
    baseline_latency_ms: float
    scenario_latency_ms: float
    latency_delta_ms: float
    baseline_cost: float
    scenario_cost: float
    cost_delta: float
    recommendation: str  # "adopt", "reject", "inconclusive"
    confidence: str  # "high", "medium", "low"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario.name,
            "scenario_description": self.scenario.description,
            "baseline_quality": self.baseline_quality,
            "scenario_quality": self.scenario_quality,
            "quality_delta": self.quality_delta,
            "baseline_latency_ms": self.baseline_latency_ms,
            "scenario_latency_ms": self.scenario_latency_ms,
            "latency_delta_ms": self.latency_delta_ms,
            "baseline_cost": self.baseline_cost,
            "scenario_cost": self.scenario_cost,
            "cost_delta": self.cost_delta,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "total_replayed": self.report.total_replayed,
            "timestamp": self.timestamp,
        }


class WhatIfSimulator:
    """
    Runs what-if simulations using the replay engine.

    Simulates: "If we had used policy X for all requests in window T,
    what would the quality/cost/latency outcomes have been?"
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._replay_engine = ReplayEngine(redis_client)

    async def simulate(
        self,
        scenario: SimulationScenario,
        experiment_id: str | None = None,
    ) -> SimulationResult:
        """
        Run a what-if simulation for a scenario.

        Args:
            scenario: The simulation scenario configuration.
            experiment_id: Optional experiment ID for tracking.

        Returns:
            SimulationResult with comparison metrics and recommendation.
        """
        if experiment_id is None:
            experiment_id = f"sim_{int(time.time())}"

        logger.info(
            "simulation_start scenario=%s experiment=%s",
            scenario.name,
            experiment_id,
        )

        # Run replay through the counterfactual policy
        report = await self._replay_engine.replay(
            experiment_id=experiment_id,
            policy=scenario.policy,
            policy_name=scenario.name,
            start_time=scenario.start_time,
            end_time=scenario.end_time,
            max_records=scenario.max_records,
        )

        # Compute deltas and recommendation
        quality_delta = report.quality_improvement
        latency_delta = report.latency_change_ms
        cost_delta = report.cost_change

        recommendation, confidence = self._evaluate_recommendation(
            quality_delta, latency_delta, cost_delta, report.total_replayed
        )

        result = SimulationResult(
            scenario=scenario,
            report=report,
            baseline_quality=report.mean_original_quality,
            scenario_quality=report.mean_counterfactual_quality,
            quality_delta=quality_delta,
            baseline_latency_ms=report.mean_original_latency_ms,
            scenario_latency_ms=report.mean_counterfactual_latency_ms,
            latency_delta_ms=latency_delta,
            baseline_cost=report.mean_original_cost,
            scenario_cost=report.mean_counterfactual_cost,
            cost_delta=cost_delta,
            recommendation=recommendation,
            confidence=confidence,
        )

        # Store result
        await self._store_simulation_result(experiment_id, result)

        logger.info(
            "simulation_complete scenario=%s quality_delta=%.4f recommendation=%s confidence=%s",
            scenario.name,
            quality_delta,
            recommendation,
            confidence,
        )

        return result

    async def compare_scenarios(
        self,
        scenarios: list[SimulationScenario],
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> list[SimulationResult]:
        """
        Compare multiple scenarios against the same time window.

        Args:
            scenarios: List of scenarios to compare.
            start_time: Shared time window start.
            end_time: Shared time window end.

        Returns:
            List of SimulationResult sorted by quality_delta descending.
        """
        results: list[SimulationResult] = []

        for scenario in scenarios:
            # Override time window if provided
            if start_time is not None:
                scenario.start_time = start_time
            if end_time is not None:
                scenario.end_time = end_time

            try:
                result = await self.simulate(scenario)
                results.append(result)
            except (TypeError, ValueError):
                logger.exception("compare_scenario_error scenario=%s", scenario.name)

        # Sort by quality improvement
        results.sort(key=lambda r: r.quality_delta, reverse=True)
        return results

    def _evaluate_recommendation(
        self,
        quality_delta: float,
        latency_delta_ms: float,
        cost_delta: float,
        sample_count: int,
    ) -> tuple[str, str]:
        """
        Evaluate whether a scenario should be adopted.

        Returns (recommendation, confidence).
        """
        # Need sufficient samples for confidence
        if sample_count < 20:
            return "inconclusive", "low"
        confidence = "medium" if sample_count < 100 else "high"

        # Quality improvement is the primary signal
        if quality_delta > 0.05 and latency_delta_ms < 500 and cost_delta < 0.01:
            return "adopt", confidence

        if quality_delta < -0.05:
            return "reject", confidence

        if quality_delta > 0.02:
            return "adopt", "medium" if confidence == "high" else "low"

        if quality_delta < -0.02:
            return "reject", "medium" if confidence == "high" else "low"

        return "inconclusive", confidence

    async def _store_simulation_result(
        self, experiment_id: str, result: SimulationResult
    ) -> None:
        """Store simulation result in Redis."""
        try:
            key = f"{SIMULATION_RESULTS_KEY}:{experiment_id}"
            data = json.dumps(result.to_dict())
            await self._redis.set(key, data, ex=86400 * 7)
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("store_simulation_error")

    async def get_simulation_result(self, experiment_id: str) -> dict[str, Any] | None:
        """Retrieve a stored simulation result."""
        try:
            key = f"{SIMULATION_RESULTS_KEY}:{experiment_id}"
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("get_simulation_error")
        return None

    async def list_simulations(self, count: int = 20) -> list[dict[str, Any]]:
        """List recent simulation results."""
        try:
            pattern = f"{SIMULATION_RESULTS_KEY}:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern, count=200):
                keys.append(key)

            results: list[dict[str, Any]] = []
            for key in sorted(keys, reverse=True)[:count]:
                data = await self._redis.get(key)
                if data:
                    results.append(json.loads(data))
            return results
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("list_simulations_error")
            return []
