"""
FreeRelay — Rate Limiting Middleware (§4)
============================================
Token bucket rate limiting per client.
Uses in-memory state (Redis-backed in production).
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("freerelay.rate_limit")

# Pre-compiled set of path prefixes to skip rate limiting
_SKIP_PATHS = frozenset({"/health", "/ready", "/dashboard", "/metrics"})

# Maximum number of client buckets to prevent memory exhaustion
_MAX_BUCKETS = 10_000

# Cleanup interval - clean stale buckets every N requests
_CLEANUP_INTERVAL = 1000


class TokenBucket:
    """
    Token bucket rate limiter.

    Refills tokens at a steady rate up to a maximum capacity.
    Each request consumes one token.
    """

    __slots__ = ("rate", "capacity", "tokens", "last_refill")

    def __init__(self, rate: float, capacity: int) -> None:
        """
        Args:
            rate: Tokens added per second.
            capacity: Maximum tokens (burst capacity).
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def consume(self) -> bool:
        """
        Try to consume one token.

        Returns:
            True if a token was available (request allowed).
            False if no tokens (request should be rate limited).
        """
        now = time.time()
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-client rate limiting using token bucket algorithm.

    Clients are identified by IP address.
    Limits are applied to /v1/* endpoints.
    Uses OrderedDict for O(1) access and LRU-style eviction.
    """

    def __init__(
        self,
        app: object,
        requests_per_minute: int = 60,
        burst_capacity: int = 10,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be at least 1")
        if burst_capacity < 1:
            raise ValueError("burst_capacity must be at least 1")

        super().__init__(app)  # type: ignore[arg-type]
        self.requests_per_minute = requests_per_minute
        self.burst_capacity = burst_capacity
        self._buckets: OrderedDict[str, TokenBucket] = OrderedDict()
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._request_count = 0

    def _get_bucket(self, client_ip: str) -> TokenBucket:
        """Get or create a token bucket for a client with LRU eviction."""
        bucket = self._buckets.get(client_ip)
        if bucket is not None:
            # Move to end for LRU ordering
            self._buckets.move_to_end(client_ip)
            return bucket

        # Evict oldest bucket if at capacity
        if len(self._buckets) >= _MAX_BUCKETS:
            self._buckets.popitem(last=False)

        bucket = TokenBucket(rate=self._rate, capacity=self.burst_capacity)
        self._buckets[client_ip] = bucket
        return bucket

    def _cleanup_stale_buckets(self) -> None:
        """Remove buckets that haven't been used in over 5 minutes."""
        now = time.time()
        stale_threshold = 300.0  # 5 minutes
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.last_refill > stale_threshold
        ]
        for key in stale_keys:
            del self._buckets[key]
        if stale_keys:
            logger.debug("Cleaned up %d stale rate limit buckets", len(stale_keys))

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only rate limit API endpoints
        path = request.url.path
        if not path.startswith("/v1/"):
            return await call_next(request)

        # Skip health/dashboard/metrics - use frozenset for O(1) lookup
        if any(path.startswith(p) for p in _SKIP_PATHS):
            return await call_next(request)

        # Periodic cleanup of stale buckets
        self._request_count += 1
        if self._request_count % _CLEANUP_INTERVAL == 0:
            self._cleanup_stale_buckets()

        # Identify by user_id if available (from AuthMiddleware), otherwise IP
        user_id = getattr(request.state, "user_id", None)
        client_id = user_id or (request.client.host if request.client else "unknown")
        bucket = self._get_bucket(client_id)

        if not bucket.consume():
            logger.warning("Rate limit exceeded for %s", client_id)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": "Rate limit exceeded. Try again later.",
                        "type": "rate_limit_error",
                        "code": 429,
                    }
                },
                headers={
                    "Retry-After": "1",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        return await call_next(request)
