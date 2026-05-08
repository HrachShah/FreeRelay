"""
FreeRelay Data Plane — Idempotency (§3.4)
============================================
Request-ID deduplication using Redis SETNX + GET.
300s default TTL. In-memory fallback when Redis unavailable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import redis
if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("freerelay.data_plane.idempotency")


@dataclass
class IdempotencyEntry:
    """Stored idempotent response."""

    request_id: str
    response: bytes
    created_at: float
    ttl: int


class IdempotencyStore:
    """
    Idempotency store using Redis SETNX + GET pattern.

    On first request with a given Request-ID:
      1. SETNX stores the key with a TTL.
      2. Subsequent requests with the same ID get the cached response.

    In-memory fallback for development/testing without Redis.
    """

    def __init__(
        self,
        redis: Redis | None = None,
        ttl: int = 300,
        key_prefix: str = "freerelay:idempotent:",
    ) -> None:
        self._redis = redis
        self._ttl = ttl
        self._key_prefix = key_prefix
        self._memory_store: dict[str, IdempotencyEntry] = {}

    def _make_key(self, request_id: str) -> str:
        return f"{self._key_prefix}{request_id}"

    async def check(self, request_id: str) -> dict[str, Any] | None:
        """
        Check if a request_id has already been processed.

        Args:
            request_id: The idempotency key from the request header.

        Returns:
            The cached response dict if found, None otherwise.
        """
        if not request_id:
            return None

        if self._redis is not None:
            try:
                return await self._check_redis(request_id)
            except (redis.ConnectionError, redis.ResponseError):
                logger.exception("Redis idempotency check failed, using fallback")
                return self._check_memory(request_id)

        return self._check_memory(request_id)

    async def _check_redis(self, request_id: str) -> dict[str, Any] | None:
        """Check Redis for an existing idempotency entry."""
        key = self._make_key(request_id)
        data = await self._redis.get(key)
        if data is not None:
            import json

            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        return None

    def _check_memory(self, request_id: str) -> dict[str, Any] | None:
        """Check in-memory store for an existing entry."""
        entry = self._memory_store.get(request_id)
        if entry is None:
            return None
        if time.time() > entry.created_at + entry.ttl:
            del self._memory_store[request_id]
            return None
        import json

        return json.loads(entry.response.decode("utf-8"))

    async def store(self, request_id: str, response: dict[str, Any]) -> bool:
        """
        Store a response for future idempotent retrieval.

        Uses SETNX to ensure only the first writer wins.

        Args:
            request_id: The idempotency key.
            response: The response to cache.

        Returns:
            True if this is the first store (won the race).
            False if the key already existed.
        """
        if not request_id:
            return True

        import json

        data = json.dumps(response).encode("utf-8")

        if self._redis is not None:
            try:
                return await self._store_redis(request_id, data)
            except (redis.ConnectionError, redis.ResponseError):
                logger.exception("Redis idempotency store failed, using fallback")
                return self._store_memory(request_id, data)

        return self._store_memory(request_id, data)

    async def _store_redis(self, request_id: str, data: bytes) -> bool:
        """Store in Redis using SETNX for atomic first-writer-wins."""
        key = self._make_key(request_id)
        # SETNX returns True if key was set, False if it already existed
        was_set = await self._redis.set(key, data, ex=self._ttl, nx=True)
        return was_set is True

    def _store_memory(self, request_id: str, data: bytes) -> bool:
        """Store in memory, first-writer-wins."""
        if request_id in self._memory_store:
            entry = self._memory_store[request_id]
            if time.time() <= entry.created_at + entry.ttl:
                return False

        self._memory_store[request_id] = IdempotencyEntry(
            request_id=request_id,
            response=data,
            created_at=time.time(),
            ttl=self._ttl,
        )
        return True

    async def delete(self, request_id: str) -> None:
        """Remove an idempotency entry (e.g. on processing failure)."""
        if self._redis is not None:
            key = self._make_key(request_id)
            await self._redis.delete(key)
        self._memory_store.pop(request_id, None)

    def cleanup_expired(self) -> int:
        """Remove expired in-memory entries. Returns count removed."""
        now = time.time()
        expired = [
            k for k, v in self._memory_store.items() if now > v.created_at + v.ttl
        ]
        for k in expired:
            del self._memory_store[k]
        return len(expired)
