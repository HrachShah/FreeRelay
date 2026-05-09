"""
FreeRelay — Capability Updater
=================================
Aggregates outcome records into capability metric updates.
Updates TTFT percentiles, schema compliance, and quality-by-task-family.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from freerelay.control_plane.learner.outcome_consumer import OutcomeRecord

logger = logging.getLogger(__name__)

CAPABILITY_KEY_PREFIX = "freerelay:capability"
PERCENTILE_WINDOW = 500  # keep last N latency values for percentile calc


class CapabilityUpdater:
    """
    Updates capability metrics from outcome records.

    Tracks per-provider metric windows in Redis and periodically
    recomputes aggregated statistics (p50/p95/p99, compliance rates, etc.).
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def process_outcome(self, outcome: OutcomeRecord) -> None:
        """
        Process a single outcome record and update relevant capability metrics.
        """
        provider = outcome.provider_chosen
        model = outcome.model_chosen
        if not provider or not model:
            return

        try:
            # Update TTFT latency window
            if outcome.ttft_ms > 0:
                await self._append_latency(provider, model, outcome.ttft_ms)

            # Update schema compliance tracking
            if outcome.schema_valid is not None:
                await self._update_schema_compliance(
                    provider, model, outcome.schema_valid
                )

            # Update quality by task family
            if outcome.judge_score > 0:
                await self._update_quality_by_task(
                    provider, model, outcome.task_family, outcome.judge_score
                )

        except (redis.ConnectionError, redis.ResponseError):
            logger.exception(
                "process_outcome_error provider=%s model=%s", provider, model
            )

    async def process_outcome_batch(self, outcomes: list[OutcomeRecord]) -> None:
        """Process a batch of outcome records efficiently."""
        if not outcomes:
            return

        # Group outcomes by provider:model
        grouped: dict[str, list[OutcomeRecord]] = {}
        for outcome in outcomes:
            key = f"{outcome.provider_chosen}:{outcome.model_chosen}"
            grouped.setdefault(key, []).append(outcome)

        for pm_key, batch in grouped.items():
            provider, model = pm_key.split(":", 1)
            await self._process_provider_batch(provider, model, batch)

    async def _process_provider_batch(
        self,
        provider: str,
        model: str,
        outcomes: list[OutcomeRecord],
    ) -> None:
        """Process a batch of outcomes for a single provider/model."""
        try:
            pipe = self._redis.pipeline()

            # Batch append TTFT values
            ttft_values = [str(o.ttft_ms) for o in outcomes if o.ttft_ms > 0]
            if ttft_values:
                lat_key = f"freerelay:cap_metrics:{provider}:{model}:ttft"
                for v in ttft_values:
                    pipe.lpush(lat_key, v)
                pipe.ltrim(lat_key, 0, PERCENTILE_WINDOW - 1)

            # Batch schema compliance
            schema_results = [
                o.schema_valid for o in outcomes if o.schema_valid is not None
            ]
            if schema_results:
                sc_key = f"freerelay:cap_metrics:{provider}:{model}:schema_valid"
                for s in schema_results:
                    pipe.lpush(sc_key, str(int(s)))
                pipe.ltrim(sc_key, 0, PERCENTILE_WINDOW - 1)

            # Batch quality scores per task family
            quality_by_task: dict[str, list[float]] = {}
            for o in outcomes:
                quality_by_task.setdefault(o.task_family, []).append(o.judge_score)

            for task_fam, scores in quality_by_task.items():
                q_key = f"freerelay:cap_metrics:{provider}:{model}:quality:{task_fam}"
                for s in scores:
                    pipe.lpush(q_key, str(s))
                pipe.ltrim(q_key, 0, PERCENTILE_WINDOW - 1)

            await pipe.execute()

            # Recompute aggregates
            await self._recompute_provider_stats(provider, model)

        except (redis.ConnectionError, redis.ResponseError):
            logger.exception(
                "process_provider_batch_error provider=%s model=%s", provider, model
            )

    async def _append_latency(self, provider: str, model: str, ttft_ms: float) -> None:
        """Append a TTFT value to the latency window."""
        key = f"freerelay:cap_metrics:{provider}:{model}:ttft"
        pipe = self._redis.pipeline()
        pipe.lpush(key, str(ttft_ms))
        pipe.ltrim(key, 0, PERCENTILE_WINDOW - 1)
        await pipe.execute()

    async def _update_schema_compliance(
        self, provider: str, model: str, valid: bool
    ) -> None:
        """Append a schema validation result."""
        key = f"freerelay:cap_metrics:{provider}:{model}:schema_valid"
        pipe = self._redis.pipeline()
        pipe.lpush(key, str(int(valid)))
        pipe.ltrim(key, 0, PERCENTILE_WINDOW - 1)
        await pipe.execute()

    async def _update_quality_by_task(
        self, provider: str, model: str, task_family: str, score: float
    ) -> None:
        """Append a quality score for a task family."""
        key = f"freerelay:cap_metrics:{provider}:{model}:quality:{task_family}"
        pipe = self._redis.pipeline()
        pipe.lpush(key, str(score))
        pipe.ltrim(key, 0, PERCENTILE_WINDOW - 1)
        await pipe.execute()

    async def _recompute_provider_stats(self, provider: str, model: str) -> None:
        """Recompute all aggregated stats and update the capability record."""
        cap_key = f"{CAPABILITY_KEY_PREFIX}:{provider}:{model}"

        try:
            # Check capability record exists
            exists = await self._redis.exists(cap_key)
            if not exists:
                return

            # TTFT percentiles
            lat_key = f"freerelay:cap_metrics:{provider}:{model}:ttft"
            raw_lat = await self._redis.lrange(lat_key, 0, -1)
            if raw_lat:
                latencies = sorted(float(v) for v in raw_lat)
                p50 = _percentile(latencies, 50)
                p95 = _percentile(latencies, 95)
                p99 = _percentile(latencies, 99)
                await self._redis.hset(
                    cap_key,
                    mapping={
                        "p50_ttft_ms": str(p50),
                        "p95_ttft_ms": str(p95),
                        "p99_ttft_ms": str(p99),
                    },
                )

            # Schema compliance rate
            sc_key = f"freerelay:cap_metrics:{provider}:{model}:schema_valid"
            raw_sc = await self._redis.lrange(sc_key, 0, -1)
            if raw_sc:
                valid_count = sum(1 for v in raw_sc if v == "1")
                rate = valid_count / len(raw_sc)
                await self._redis.hset(cap_key, "schema_compliance_rate", str(rate))

            # Quality by task family
            quality_keys = await self._redis.keys(
                f"freerelay:cap_metrics:{provider}:{model}:quality:*"
            )
            quality_map: dict[str, float] = {}
            for q_key in quality_keys:
                task_fam = q_key.split(":")[-1]
                raw_scores = await self._redis.lrange(q_key, 0, -1)
                if raw_scores:
                    scores = [float(s) for s in raw_scores]
                    quality_map[task_fam] = sum(scores) / len(scores)

            if quality_map:
                await self._redis.hset(
                    cap_key, "quality_by_task_family", json.dumps(quality_map)
                )

            await self._redis.hset(cap_key, "last_updated_ts", str(time.time()))

        except (redis.ConnectionError, redis.ResponseError):
            logger.exception(
                "recompute_stats_error provider=%s model=%s", provider, model
            )

    async def get_provider_stats(self, provider: str, model: str) -> dict[str, Any]:
        """Retrieve current capability stats for a provider/model."""
        cap_key = f"{CAPABILITY_KEY_PREFIX}:{provider}:{model}"
        try:
            data = await self._redis.hgetall(cap_key)
            if not data:
                return {}
            return {
                "provider": provider,
                "model": model,
                "p50_ttft_ms": float(data.get("p50_ttft_ms", 0)),
                "p95_ttft_ms": float(data.get("p95_ttft_ms", 0)),
                "p99_ttft_ms": float(data.get("p99_ttft_ms", 0)),
                "schema_compliance_rate": float(
                    data.get("schema_compliance_rate", 1.0)
                ),
                "quality_by_task_family": _safe_json_load(
                    data.get("quality_by_task_family"), {}
                ),
                "latency_degraded": data.get("latency_degraded", "False") == "True",
                "error_rate_degraded": data.get("error_rate_degraded", "False")
                == "True",
                "last_updated_ts": float(data.get("last_updated_ts", 0)),
            }
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("get_stats_error provider=%s model=%s", provider, model)
            return {}


def _safe_json_load(data: Any, default: Any) -> Any:
    """Safely load JSON from data, returning default on failure."""
    try:
        return json.loads(data) if data is not None else default
    except (json.JSONDecodeError, TypeError):
        return default


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute a percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[f]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
