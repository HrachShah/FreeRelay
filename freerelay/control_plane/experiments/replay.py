"""
FreeRelay — Replay Engine
============================
Replays historical outcome records through a new routing engine in dry-run mode.
Emits counterfactual OutcomeRecords for comparison.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

from freerelay.control_plane.learner.outcome_consumer import OutcomeRecord

logger = logging.getLogger(__name__)

REPLAY_RESULTS_KEY = "freerelay:experiment:replay"
OUTCOME_STREAM = "freerelay:outcomes"


@dataclass
class CounterfactualOutcome:
    """A counterfactual outcome produced by replaying a request through a different policy."""

    original_request_id: str
    original_provider: str
    original_model: str
    counterfactual_provider: str
    counterfactual_model: str
    original_quality: float
    counterfactual_quality: float  # estimated
    original_latency_ms: float
    counterfactual_latency_ms: float  # estimated
    original_cost: float
    counterfactual_cost: float  # estimated
    quality_delta: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_request_id": self.original_request_id,
            "original_provider": self.original_provider,
            "original_model": self.original_model,
            "counterfactual_provider": self.counterfactual_provider,
            "counterfactual_model": self.counterfactual_model,
            "original_quality": self.original_quality,
            "counterfactual_quality": self.counterfactual_quality,
            "original_latency_ms": self.original_latency_ms,
            "counterfactual_latency_ms": self.counterfactual_latency_ms,
            "original_cost": self.original_cost,
            "counterfactual_cost": self.counterfactual_cost,
            "quality_delta": self.quality_delta,
            "timestamp": self.timestamp,
        }


@dataclass
class ReplayReport:
    """Aggregated comparison report from a replay run."""

    experiment_id: str
    policy_name: str
    total_replayed: int
    mean_original_quality: float
    mean_counterfactual_quality: float
    quality_improvement: float
    mean_original_latency_ms: float
    mean_counterfactual_latency_ms: float
    latency_change_ms: float
    mean_original_cost: float
    mean_counterfactual_cost: float
    cost_change: float
    counterfactuals: list[CounterfactualOutcome] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "policy_name": self.policy_name,
            "total_replayed": self.total_replayed,
            "mean_original_quality": self.mean_original_quality,
            "mean_counterfactual_quality": self.mean_counterfactual_quality,
            "quality_improvement": self.quality_improvement,
            "mean_original_latency_ms": self.mean_original_latency_ms,
            "mean_counterfactual_latency_ms": self.mean_counterfactual_latency_ms,
            "latency_change_ms": self.latency_change_ms,
            "mean_original_cost": self.mean_original_cost,
            "mean_counterfactual_cost": self.mean_counterfactual_cost,
            "cost_change": self.cost_change,
            "timestamp": self.timestamp,
        }


class ReplayEngine:
    """
    Replays historical outcomes through a new routing engine (dry-run mode).

    Loads outcome records from the Redis stream, applies a counterfactual
    routing policy, and produces comparison reports.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        routing_engine: Any | None = None,
    ) -> None:
        self._redis = redis_client
        self._routing_engine = routing_engine

    async def load_outcomes(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        max_records: int = 1000,
    ) -> list[OutcomeRecord]:
        """
        Load outcome records from the Redis stream for a time window.

        Args:
            start_time: Unix timestamp start (inclusive). None = no lower bound.
            end_time: Unix timestamp end (inclusive). None = no upper bound.
            max_records: Maximum records to load.

        Returns:
            List of OutcomeRecord within the time window.
        """
        records: list[OutcomeRecord] = []
        try:
            # Read from stream (use XRANGE for historical data)
            start_id = "0" if start_time is None else f"{int(start_time * 1000)}-0"
            end_id = "+" if end_time is None else f"{int(end_time * 1000)}-0"

            results = await self._redis.xrange(
                OUTCOME_STREAM,
                min=start_id,
                max=end_id,
                count=max_records,
            )

            for msg_id, fields in results:
                record = OutcomeRecord.from_stream(msg_id, fields)
                records.append(record)

            logger.info("replay_loaded_outcomes count=%d", len(records))

        except Exception:
            logger.exception("load_outcomes_error")

        return records

    async def replay(
        self,
        experiment_id: str,
        policy: dict[str, Any],
        policy_name: str = "counterfactual",
        start_time: float | None = None,
        end_time: float | None = None,
        max_records: int = 1000,
    ) -> ReplayReport:
        """
        Replay outcomes through a counterfactual policy.

        Args:
            experiment_id: Identifier for this replay experiment.
            policy: The counterfactual routing policy to test.
            policy_name: Human-readable name for the policy.
            start_time: Time window start.
            end_time: Time window end.
            max_records: Max records to replay.

        Returns:
            ReplayReport with aggregate comparison metrics.
        """
        outcomes = await self.load_outcomes(start_time, end_time, max_records)
        counterfactuals: list[CounterfactualOutcome] = []

        for outcome in outcomes:
            cf = await self._compute_counterfactual(outcome, policy)
            if cf:
                counterfactuals.append(cf)

        report = self._build_report(experiment_id, policy_name, counterfactuals)

        # Store report
        await self._store_report(experiment_id, report)

        logger.info(
            "replay_complete experiment=%s replayed=%d quality_delta=%.4f",
            experiment_id,
            len(counterfactuals),
            report.quality_improvement,
        )

        return report

    async def _compute_counterfactual(
        self,
        outcome: OutcomeRecord,
        policy: dict[str, Any],
    ) -> CounterfactualOutcome | None:
        """
        Compute what would have happened under a different routing policy.
        """
        try:
            # Determine counterfactual provider/model
            if self._routing_engine:
                cf_route = await self._routing_engine.route(
                    task_family=outcome.task_family,
                    policy=policy,
                    exclude_providers=[outcome.provider_chosen],
                )
                cf_provider = cf_route.get("provider", outcome.provider_chosen)
                cf_model = cf_route.get("model", outcome.model_chosen)
            else:
                # Simple counterfactual: pick first alternate from policy
                alternatives = policy.get("prefer", [])
                if alternatives and alternatives[0] != outcome.provider_chosen:
                    cf_provider = alternatives[0]
                    cf_model = outcome.model_chosen
                else:
                    return None

            # Estimate counterfactual quality (use existing bandit data or heuristic)
            original_quality = outcome.judge_score
            cf_quality = await self._estimate_quality(
                cf_provider, cf_model, outcome.task_family
            )

            # Estimate counterfactual latency (from capability registry or heuristic)
            original_latency = outcome.latency_ms
            cf_latency = await self._estimate_latency(cf_provider, cf_model)

            # Estimate cost (simplified)
            original_cost = outcome.tokens_in * 0.001 + outcome.tokens_out * 0.002
            cf_cost = original_cost * 1.1  # placeholder multiplier

            return CounterfactualOutcome(
                original_request_id=outcome.request_id,
                original_provider=outcome.provider_chosen,
                original_model=outcome.model_chosen,
                counterfactual_provider=cf_provider,
                counterfactual_model=cf_model,
                original_quality=original_quality,
                counterfactual_quality=cf_quality,
                original_latency_ms=original_latency,
                counterfactual_latency_ms=cf_latency,
                original_cost=original_cost,
                counterfactual_cost=cf_cost,
                quality_delta=cf_quality - original_quality,
            )

        except Exception:
            logger.exception("counterfactual_error request=%s", outcome.request_id)
            return None

    async def _estimate_quality(
        self, provider: str, model: str, task_family: str
    ) -> float:
        """Estimate quality for a provider/model/task combo from bandit data."""
        try:
            key = f"freerelay:bandit:{provider}:{model}:{task_family}"
            data = await self._redis.hgetall(key)
            if data:
                raw = data.get("ewma_quality", "0.5")
                return float(raw)
        except (ValueError, TypeError):
            pass
        return 0.5  # neutral prior

    async def _estimate_latency(self, provider: str, model: str) -> float:
        """Estimate latency from capability registry."""
        try:
            key = f"freerelay:capability:{provider}:{model}"
            data = await self._redis.hgetall(key)
            if data:
                raw = data.get("p50_ttft_ms", "100.0")
                return float(raw)
        except (ValueError, TypeError):
            pass
        return 100.0  # default estimate

    def _build_report(
        self,
        experiment_id: str,
        policy_name: str,
        counterfactuals: list[CounterfactualOutcome],
    ) -> ReplayReport:
        """Build an aggregate replay report from counterfactuals."""
        n = len(counterfactuals)
        if n == 0:
            return ReplayReport(
                experiment_id=experiment_id,
                policy_name=policy_name,
                total_replayed=0,
                mean_original_quality=0.0,
                mean_counterfactual_quality=0.0,
                quality_improvement=0.0,
                mean_original_latency_ms=0.0,
                mean_counterfactual_latency_ms=0.0,
                latency_change_ms=0.0,
                mean_original_cost=0.0,
                mean_counterfactual_cost=0.0,
                cost_change=0.0,
            )

        mq_orig = sum(c.original_quality for c in counterfactuals) / n
        mq_cf = sum(c.counterfactual_quality for c in counterfactuals) / n
        ml_orig = sum(c.original_latency_ms for c in counterfactuals) / n
        ml_cf = sum(c.counterfactual_latency_ms for c in counterfactuals) / n
        mc_orig = sum(c.original_cost for c in counterfactuals) / n
        mc_cf = sum(c.counterfactual_cost for c in counterfactuals) / n

        return ReplayReport(
            experiment_id=experiment_id,
            policy_name=policy_name,
            total_replayed=n,
            mean_original_quality=mq_orig,
            mean_counterfactual_quality=mq_cf,
            quality_improvement=mq_cf - mq_orig,
            mean_original_latency_ms=ml_orig,
            mean_counterfactual_latency_ms=ml_cf,
            latency_change_ms=ml_cf - ml_orig,
            mean_original_cost=mc_orig,
            mean_counterfactual_cost=mc_cf,
            cost_change=mc_cf - mc_orig,
            counterfactuals=counterfactuals,
        )

    async def _store_report(self, experiment_id: str, report: ReplayReport) -> None:
        """Store the replay report in Redis."""
        try:
            key = f"{REPLAY_RESULTS_KEY}:{experiment_id}"
            data = json.dumps(report.to_dict())
            await self._redis.set(key, data, ex=86400 * 7)  # 7 day TTL
        except Exception:
            logger.exception("store_report_error")

    async def get_report(self, experiment_id: str) -> dict[str, Any] | None:
        """Retrieve a stored replay report."""
        try:
            key = f"{REPLAY_RESULTS_KEY}:{experiment_id}"
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
        except Exception:
            logger.exception("get_report_error")
        return None
