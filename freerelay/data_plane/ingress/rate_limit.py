"""
FreeRelay Data Plane — Rate Limiting (§4)
============================================
Sliding window counter per namespace using Redis Lua script.
In-memory fallback when Redis is unavailable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("freerelay.data_plane.rate_limit")

# Lua script for atomic sliding window counter
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove entries outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, now .. ':' .. math.random(1000000))
    redis.call('EXPIRE', key, window + 1)
    return {1, limit - count - 1, math.ceil(now + window)}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_ts = now + window
    if oldest[2] then
        reset_ts = tonumber(oldest[2]) + window
    end
    return {0, 0, math.ceil(reset_ts)}
end
"""


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_ts: int
    limit: int


class _InMemoryWindow:
    """In-memory sliding window fallback."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = {}

    def check(self, namespace: str, limit: int, window: float) -> RateLimitResult:
        now = time.time()
        cutoff = now - window

        timestamps = self._windows.get(namespace, [])
        timestamps = [ts for ts in timestamps if ts > cutoff]

        if len(timestamps) < limit:
            timestamps.append(now)
            self._windows[namespace] = timestamps
            remaining = limit - len(timestamps)
            reset_ts = int(now + window)
            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                reset_ts=reset_ts,
                limit=limit,
            )

        self._windows[namespace] = timestamps
        oldest = min(timestamps) if timestamps else now
        reset_ts = int(oldest + window)
        return RateLimitResult(
            allowed=False,
            remaining=0,
            reset_ts=reset_ts,
            limit=limit,
        )


class RateLimiter:
    """
    Sliding window rate limiter.

    Uses Redis sorted sets with a Lua script for atomic operations.
    Falls back to in-memory tracking when Redis is unavailable.
    """

    def __init__(
        self,
        redis: Redis | None = None,
        window_seconds: int = 60,
        key_prefix: str = "freerelay:ratelimit:",
    ) -> None:
        self._redis = redis
        self._window = window_seconds
        self._key_prefix = key_prefix
        self._fallback = _InMemoryWindow()
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        """Load the Lua script into Redis, caching the SHA."""
        if self._script_sha is not None:
            return self._script_sha
        if self._redis is None:
            raise RuntimeError("Redis not available")
        self._script_sha = await self._redis.script_load(_SLIDING_WINDOW_LUA)
        return self._script_sha

    async def check_rate_limit(
        self,
        namespace: str,
        limit: int,
    ) -> RateLimitResult:
        """
        Check if a request is within the rate limit.

        Args:
            namespace: The tenant/namespace to rate limit.
            limit: Maximum requests allowed in the window.

        Returns:
            RateLimitResult with allowed status and metadata.
        """
        if self._redis is not None:
            try:
                return await self._check_redis(namespace, limit)
            except redis.exceptions.RedisError:
                logger.exception("Redis rate limit check failed, using fallback")
                return self._fallback.check(namespace, limit, self._window)

        return self._fallback.check(namespace, limit, self._window)

    async def _check_redis(self, namespace: str, limit: int) -> RateLimitResult:
        """Execute the sliding window Lua script in Redis."""
        sha = await self._ensure_script()
        key = f"{self._key_prefix}{namespace}"
        now = time.time()

        result = await self._redis.evalsha(
            sha, 1, key, str(now), str(self._window), str(limit)
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        reset_ts = int(result[2])

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_ts=reset_ts,
            limit=limit,
        )

    async def reset(self, namespace: str) -> None:
        """Reset the rate limit for a namespace."""
        if self._redis is not None:
            key = f"{self._key_prefix}{namespace}"
            await self._redis.delete(key)
        self._fallback._windows.pop(namespace, None)
