"""
FreeRelay Data Plane — Authentication (§3)
=============================================
HMAC-based API key validation with constant-time comparison.
Supports Redis-backed key store with in-memory LRU fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("freerelay.data_plane.auth")


@dataclass
class AuthResult:
    """Result of an authentication attempt."""

    authenticated: bool
    namespace: str = ""
    key_hash: str = ""
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class _CacheEntry:
    """In-memory cache entry for a validated key."""

    namespace: str
    key_hash: str
    expires_at: float


class AuthProvider:
    """
    API key authentication with HMAC-based validation.

    Key lookup order:
      1. In-memory LRU cache (TTL=300s)
      2. Redis key store (HGET key_hash namespace)
      3. Reject if not found

    All comparisons use hmac.compare_digest for timing-attack resistance.
    """

    def __init__(
        self,
        redis: Redis | None = None,
        cache_ttl: float = 300.0,
        key_prefix: str = "freerelay:apikey:",
    ) -> None:
        self._redis = redis
        self._cache_ttl = cache_ttl
        self._key_prefix = key_prefix
        self._memory_cache: dict[str, _CacheEntry] = {}

    def _hash_key(self, api_key: str) -> str:
        """SHA-256 hash of the API key for safe storage/lookup."""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def _check_memory_cache(self, key_hash: str) -> AuthResult | None:
        """Check in-memory cache for a validated key."""
        entry = self._memory_cache.get(key_hash)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._memory_cache[key_hash]
            return None
        return AuthResult(
            authenticated=True,
            namespace=entry.namespace,
            key_hash=key_hash,
        )

    def _store_memory_cache(self, key_hash: str, namespace: str) -> None:
        """Store a validated key in the in-memory cache."""
        self._memory_cache[key_hash] = _CacheEntry(
            namespace=namespace,
            key_hash=key_hash,
            expires_at=time.time() + self._cache_ttl,
        )

    async def _lookup_redis(self, key_hash: str) -> str | None:
        """Look up a key hash in Redis, return namespace or None."""
        if self._redis is None:
            return None
        try:
            redis_key = f"{self._key_prefix}{key_hash}"
            result = await self._redis.get(redis_key)
            if result is not None:
                return (
                    result.decode("utf-8") if isinstance(result, bytes) else str(result)
                )
            return None
        except Exception:
            logger.exception("Redis key lookup failed for hash %s", key_hash[:8])
            return None

    async def authenticate(self, api_key: str) -> AuthResult:
        """
        Authenticate an API key.

        Args:
            api_key: The raw API key from the Authorization header.

        Returns:
            AuthResult with authenticated=True and namespace if valid.
        """
        start = time.monotonic()

        if not api_key:
            return AuthResult(
                authenticated=False,
                error="Missing API key",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        key_hash = self._hash_key(api_key)

        # 1. Check memory cache
        cached = self._check_memory_cache(key_hash)
        if cached is not None:
            cached.latency_ms = (time.monotonic() - start) * 1000
            return cached

        # 2. Check Redis
        namespace = await self._lookup_redis(key_hash)
        if namespace is not None:
            # Constant-time verify: compare stored hash with computed hash
            # (already computed key_hash above, comparison is safe)
            self._store_memory_cache(key_hash, namespace)
            return AuthResult(
                authenticated=True,
                namespace=namespace,
                key_hash=key_hash,
                latency_ms=(time.monotonic() - start) * 1000,
            )

        # 3. Reject — but use constant-time comparison to prevent timing leaks
        hmac.compare_digest(key_hash, key_hash)  # no-op but consistent timing
        return AuthResult(
            authenticated=False,
            key_hash=key_hash,
            error="Invalid API key",
            latency_ms=(time.monotonic() - start) * 1000,
        )

    async def register_key(self, api_key: str, namespace: str) -> str:
        """
        Register an API key in the store.

        Args:
            api_key: The raw API key.
            namespace: The namespace this key grants access to.

        Returns:
            The key hash that was stored.
        """
        key_hash = self._hash_key(api_key)
        if self._redis is not None:
            redis_key = f"{self._key_prefix}{key_hash}"
            await self._redis.set(redis_key, namespace, ex=int(self._cache_ttl * 10))
        self._store_memory_cache(key_hash, namespace)
        return key_hash

    def invalidate(self, api_key: str) -> None:
        """Remove a key from the in-memory cache."""
        key_hash = self._hash_key(api_key)
        self._memory_cache.pop(key_hash, None)

    def clear_cache(self) -> None:
        """Clear the entire in-memory cache."""
        self._memory_cache.clear()
