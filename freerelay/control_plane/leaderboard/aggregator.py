from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis

from freerelay.control_plane.leaderboard.models import (
    AnomalyAlert,
    BenchmarkHistory,
    LatencyMetrics,
    LeaderboardEntry,
    LeaderboardResponse,
    OutputContract,
    QuotaState,
    SchemaCompliance,
    TaskFamily,
    TaskFamilyRanking,
)

logger = logging.getLogger("freerelay.control_plane.leaderboard")


class LeaderboardAggregator:
    """
    Aggregates anonymized outcome records and benchmark results to produce
    the public leaderboard. Runs hourly from outcome stream + benchmark data.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    async def aggregate_hourly(self) -> LeaderboardResponse:
        """
        Compute hourly leaderboard from:
        - Anonymized outcome records (last 1 hour)
        - Benchmark suite results
        - Budget/quota tracking
        - Anomaly alerts
        """
        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)

        rankings = await self._compute_task_family_rankings(hour_ago, now)
        latency_metrics = await self._compute_latency_metrics(hour_ago, now)
        schema_compliance = await self._compute_schema_compliance()
        quota_states = await self._compute_quota_states()
        benchmark_history = await self._compute_benchmark_history()
        anomaly_alerts = await self._fetch_anomaly_alerts()

        return LeaderboardResponse(
            rankings=rankings,
            latency_metrics=latency_metrics,
            schema_compliance=schema_compliance,
            quota_states=quota_states,
            benchmark_history=benchmark_history,
            anomaly_alerts=anomaly_alerts,
            generated_at=now,
        )

    async def _compute_task_family_rankings(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[TaskFamily, TaskFamilyRanking]:
        """
        Compute best provider per task_family from anonymized outcomes.
        Privacy: Only aggregated data published, no prompts/responses.
        """
        rankings: dict[TaskFamily, TaskFamilyRanking] = {}

        for task_family in TaskFamily:
            key = f"freerelay:leaderboard:hourly:{task_family.value}"
            entries_data = await self._redis.zrange(key, 0, 9, withscores=True)

            entries = []
            for rank, (provider_model, score) in enumerate(entries_data, 1):
                provider, model = provider_model.decode().split(":", 1)
                entries.append(
                    LeaderboardEntry(
                        rank=rank,
                        provider=provider,
                        model=model,
                        task_family=task_family,
                        quality_score=score,
                        latency_p50_ms=0.0,
                        latency_p95_ms=0.0,
                        schema_compliance_rate=0.0,
                        confidence=0.8,
                    )
                )

            rankings[task_family] = TaskFamilyRanking(
                task_family=task_family,
                entries=entries,
                updated_at=end,
            )

        return rankings

    async def _compute_latency_metrics(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[str, dict[str, LatencyMetrics]]:
        """
        Compute latency p50/p95/p99 by provider and model.
        """
        metrics: dict[str, dict[str, LatencyMetrics]] = {}

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match="freerelay:latency:*", count=100
            )
            for key in keys:
                key_str = key.decode()
                parts = key_str.split(":")
                if len(parts) >= 3:
                    provider, model = parts[2], parts[3] if len(parts) > 3 else ""
                    data = await self._redis.hgetall(key)
                    if data:
                        if provider not in metrics:
                            metrics[provider] = {}
                        metrics[provider][model] = LatencyMetrics(
                            p50_ms=float(data.get(b"p50", 0)),
                            p95_ms=float(data.get(b"p95", 0)),
                            p99_ms=float(data.get(b"p99", 0)),
                            sample_count=int(data.get(b"count", 0)),
                        )

            if cursor == 0:
                break

        return metrics

    async def _compute_schema_compliance(self) -> list[SchemaCompliance]:
        """
        Compute schema compliance rate by output_contract from benchmark suite.
        Nightly update - not from user traffic.
        """
        compliance = []

        for contract in OutputContract:
            key = f"freerelay:benchmark:schema:{contract.value}"
            data = await self._redis.hgetall(key)
            if data:
                total = int(data.get(b"total", 0))
                success = int(data.get(b"success", 0))
                rate = success / total if total > 0 else 0.0

                compliance.append(
                    SchemaCompliance(
                        output_contract=contract,
                        compliance_rate=rate,
                        total_attempts=total,
                        successful=success,
                    )
                )

        return compliance

    async def _compute_quota_states(self) -> list[QuotaState]:
        """
        Compute free tier quota state. Hourly update.
        Global aggregate - no per-key data.
        """
        quotas = []

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match="freerelay:quota:global:*", count=100
            )
            for key in keys:
                data = await self._redis.hgetall(key)
                if data:
                    parts = key.decode().split(":")
                    if len(parts) >= 4:
                        provider, model = parts[3], parts[4] if len(parts) > 4 else ""
                        quotas.append(
                            QuotaState(
                                provider=provider,
                                model=model,
                                quota_remaining=int(data.get(b"remaining", 0)),
                                quota_total=int(data.get(b"total", 0)),
                                hourly_updated=datetime.now(UTC),
                            )
                        )

            if cursor == 0:
                break

        return quotas

    async def _compute_benchmark_history(self) -> list[BenchmarkHistory]:
        """
        Fetch benchmark score history (30 days).
        """
        history = []

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match="freerelay:benchmark:history:*", count=100
            )
            for key in keys:
                data = await self._redis.hgetall(key)
                if data:
                    parts = key.decode().split(":")
                    if len(parts) >= 4:
                        provider, model = parts[3], parts[4] if len(parts) > 4 else ""
                        scores = []
                        for timestamp, score in data.items():
                            try:
                                ts = datetime.fromtimestamp(
                                    float(timestamp), UTC
                                )
                                scores.append((ts, float(score)))
                            except (ValueError, TypeError):
                                continue

                        history.append(
                            BenchmarkHistory(
                                provider=provider,
                                model=model,
                                suite="default",
                                scores=scores,
                                history_days=30,
                            )
                        )

            if cursor == 0:
                break

        return history

    async def _fetch_anomaly_alerts(self) -> list[AnomalyAlert]:
        """
        Fetch real-time anomaly alerts from anomaly detector.
        No user data - only provider metrics anomalies.
        """
        alerts = []

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match="freerelay:anomaly:*", count=100
            )
            for key in keys:
                data = await self._redis.hgetall(key)
                if data:
                    parts = key.decode().split(":")
                    if len(parts) >= 3:
                        provider, model = parts[2], parts[3] if len(parts) > 3 else ""
                        alerts.append(
                            AnomalyAlert(
                                provider=provider,
                                model=model,
                                anomaly_type=data.get(b"type", b"unknown").decode(),
                                detected_at=datetime.fromtimestamp(
                                    float(data.get(b"timestamp", 0)), UTC
                                ),
                                details=data.get(b"details", b"").decode() or None,
                            )
                        )

            if cursor == 0:
                break

        return alerts
