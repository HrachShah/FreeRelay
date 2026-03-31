"""
FreeRelay — Policy Publisher
==============================
Publishes the current routing policy to Redis for data-plane consumption.
Supports versioned, atomic updates via Redis Pub/Sub + persistent key.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

POLICY_KEY = "freerelay:policy:v2"
POLICY_CHANNEL = "freerelay:policy:v2"
POLICY_HISTORY_KEY = "freerelay:policy:history"
MAX_POLICY_HISTORY = 50


class PolicyPublisher:
    """
    Publishes routing policies to Redis for consumption by the data plane.

    Uses atomic SET + PUBLISH to ensure data-plane workers see consistent state.
    Maintains a version history for rollback support.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def publish(
        self,
        policy: dict[str, Any],
        reason: str = "tick_update",
    ) -> str:
        """
        Publish a policy update atomically.

        Args:
            policy: The routing policy dict.
            reason: Human-readable reason for the update.

        Returns:
            The version string of the published policy.
        """
        version = f"v{int(time.time() * 1000)}"
        policy_with_meta = {
            **policy,
            "version": version,
            "published_at": time.time(),
            "reason": reason,
        }

        serialized = json.dumps(policy_with_meta)

        try:
            # Pipeline for atomicity: SET + PUBLISH + history append
            pipe = self._redis.pipeline()
            pipe.set(POLICY_KEY, serialized)
            pipe.publish(POLICY_CHANNEL, serialized)

            # Append to version history (trim old entries)
            history_entry = json.dumps(
                {
                    "version": version,
                    "published_at": policy_with_meta["published_at"],
                    "reason": reason,
                }
            )
            pipe.lpush(POLICY_HISTORY_KEY, history_entry)
            pipe.ltrim(POLICY_HISTORY_KEY, 0, MAX_POLICY_HISTORY - 1)

            await pipe.execute()

            logger.info(
                "policy_published version=%s reason=%s keys=%d",
                version,
                reason,
                len(policy),
            )
            return version

        except Exception:
            logger.exception("policy_publish_error")
            raise

    async def load_current(self) -> dict[str, Any] | None:
        """Load the currently active policy from Redis."""
        try:
            raw = await self._redis.get(POLICY_KEY)
            if raw is None:
                return None
            return json.loads(raw)
        except (json.JSONDecodeError, Exception):
            logger.exception("policy_load_error")
            return None

    async def get_version_history(self, count: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent policy version history."""
        try:
            entries = await self._redis.lrange(POLICY_HISTORY_KEY, 0, count - 1)
            return [json.loads(e) for e in entries]
        except Exception:
            logger.exception("policy_history_error")
            return []

    async def rollback(self, target_version: str) -> bool:
        """
        Rollback to a specific policy version.
        Looks up the full policy from a versioned key.
        Returns True if rollback succeeded.
        """
        try:
            versioned_key = f"freerelay:policy:versions:{target_version}"
            raw = await self._redis.get(versioned_key)
            if raw is None:
                logger.error("rollback_version_not_found version=%s", target_version)
                return False

            policy = json.loads(raw)
            await self.publish(policy, reason=f"rollback_to_{target_version}")
            logger.info("policy_rollback version=%s", target_version)
            return True

        except Exception:
            logger.exception("rollback_error")
            return False

    async def snapshot_version(self, version: str) -> None:
        """
        Store a full snapshot of a policy version for rollback support.
        Call this after publish() if you want the version to be rollback-able.
        """
        try:
            raw = await self._redis.get(POLICY_KEY)
            if raw is None:
                return
            versioned_key = f"freerelay:policy:versions:{version}"
            await self._redis.set(versioned_key, raw, ex=86400 * 7)  # 7 day TTL
            logger.debug("policy_version_snapshot version=%s", version)
        except Exception:
            logger.exception("snapshot_version_error")

    async def subscribe_to_updates(self, callback: Any) -> None:
        """
        Subscribe to policy updates via Pub/Sub.
        callback(policy_dict) is invoked for each update.
        Primarily useful for data-plane workers.
        """
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(POLICY_CHANNEL)
            logger.info("policy_subscribed channel=%s", POLICY_CHANNEL)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        policy = json.loads(message["data"])
                        await callback(policy)
                    except Exception:
                        logger.exception("policy_callback_error")
        except Exception:
            logger.exception("policy_subscribe_error")
        finally:
            await pubsub.unsubscribe(POLICY_CHANNEL)
            await pubsub.aclose()

    async def delete_policy(self) -> bool:
        """Delete the current policy (e.g., to force reload from file)."""
        try:
            deleted = await self._redis.delete(POLICY_KEY)
            if deleted:
                logger.info("policy_deleted")
            return bool(deleted)
        except Exception:
            logger.exception("policy_delete_error")
            return False
