from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis

from freerelay.control_plane.leaderboard.models import (
    LeaderboardResponse,
    TaskFamily,
)

logger = logging.getLogger("freerelay.control_plane.leaderboard")


class LeaderboardPublisher:
    """
    Publishes the leaderboard to public-facing endpoints.
    Supports:
    - Hourly updates (latency, best provider per task family)
    - Nightly updates (benchmark-only: schema compliance, long-context recall)

    Privacy guarantees enforced:
    - No prompts or responses ever published
    - Only aggregated data from anonymized outcome records (opt-in)
    - Benchmark-only data for schema compliance and long-context recall
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    async def publish(self, leaderboard: LeaderboardResponse) -> None:
        """
        Publish the complete leaderboard to Redis and trigger webhook/API updates.
        """
        await self._publish_to_redis(leaderboard)
        await self._publish_to_api(leaderboard)
        await self._trigger_webhooks(leaderboard)

    async def _publish_to_redis(self, leaderboard: LeaderboardResponse) -> None:
        """
        Publish to Redis for API consumption.
        Key: freerelay:leaderboard:public
        TTL: 1 hour (re-generated hourly)
        """
        payload = leaderboard.model_dump_json()

        await self._redis.set(
            "freerelay:leaderboard:public",
            payload,
            ex=3600,
        )

        # Also publish per-task-family rankings
        for task_family, ranking in leaderboard.rankings.items():
            key = f"freerelay:leaderboard:task_family:{task_family.value}"
            await self._redis.set(
                key,
                ranking.model_dump_json(),
                ex=3600,
            )

        logger.info(
            "Published leaderboard at %s with %d task families",
            leaderboard.generated_at.isoformat(),
            len(leaderboard.rankings),
        )

    async def _publish_to_api(self, leaderboard: LeaderboardResponse) -> None:
        """
        Publish to API endpoint data. Could integrate with a web server.
        """
        # Store latest for polling API
        for task_family, ranking in leaderboard.rankings.items():
            entries_json = json.dumps(
                [
                    {
                        "rank": e.rank,
                        "provider": e.provider,
                        "model": e.model,
                        "quality_score": e.quality_score,
                        "latency_p50_ms": e.latency_p50_ms,
                        "latency_p95_ms": e.latency_p95_ms,
                        "schema_compliance_rate": e.schema_compliance_rate,
                    }
                    for e in ranking.entries
                ]
            )

            key = f"freerelay:api:leaderboard:{task_family.value}"
            await self._redis.set(key, entries_json, ex=3600)

    async def _trigger_webhooks(self, leaderboard: LeaderboardResponse) -> None:
        """
        Trigger webhooks for real-time leaderboard updates.
        """
        # Store webhook queue for external consumers
        webhook_data = {
            "generated_at": leaderboard.generated_at.isoformat(),
            "task_families": list(leaderboard.rankings.keys()),
            "top_provider_per_family": {
                tf.value: ranking.entries[0].provider if ranking.entries else None
                for tf, ranking in leaderboard.rankings.items()
            },
        }

        await self._redis.lpush(
            "freerelay:leaderboard:webhooks",
            json.dumps(webhook_data),
        )

        # Trim to keep only last 100
        await self._redis.ltrim("freerelay:leaderboard:webhooks", 0, 99)

    async def publish_nightly_benchmark(
        self,
        schema_compliance: list[dict[str, object]],
        long_context_scores: list[dict[str, object]],
    ) -> None:
        """
        Publish nightly benchmark-only data:
        - Schema compliance rate by output_contract
        - Long-context recall scores
        """
        key = "freerelay:leaderboard:nightly:benchmark"

        nightly_data = {
            "schema_compliance": schema_compliance,
            "long_context_recall": long_context_scores,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        await self._redis.set(
            key,
            json.dumps(nightly_data),
            ex=86400,
        )

        logger.info("Published nightly benchmark data")

    async def get_public_leaderboard(self) -> LeaderboardResponse | None:
        """
        Retrieve the current public leaderboard.
        """
        data = await self._redis.get("freerelay:leaderboard:public")
        if data:
            return LeaderboardResponse.model_validate_json(data)
        return None

    async def get_task_family_ranking(
        self, task_family: TaskFamily
    ) -> dict[str, object] | None:
        """
        Get ranking for a specific task family.
        """
        key = f"freerelay:api:leaderboard:{task_family.value}"
        data = await self._redis.get(key)
        if data:
            try:
                result: dict[str, object] = json.loads(data)
                return result
            except json.JSONDecodeError:
                logger.warning("get_task_family_ranking: corrupted data in Redis for key=%s", key)
        return None
