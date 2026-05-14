"""
FreeRelay — Idempotency Middleware (§4)
==========================================
Deduplicates requests using idempotency keys.
Prevents duplicate processing of retried requests.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("freerelay.idempotency")

# Maximum number of cached idempotency keys
_MAX_CACHE_SIZE = 5000

# Cleanup interval - clean expired entries every N requests
_CLEANUP_INTERVAL = 500


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Idempotency key deduplication middleware.

    Clients can send an X-Idempotency-Key header to prevent
    duplicate processing of retried requests.

    Cached responses are stored for 10 minutes.
    Uses OrderedDict for O(1) access and automatic LRU eviction.
    """

    def __init__(self, app: object, ttl: int = 600) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple[float, dict[str, object], int]] = (
            OrderedDict()
        )
        self._request_count = 0

    def _cleanup_expired(self) -> None:
        """Remove expired idempotency entries efficiently."""
        now = time.time()
        expired_keys = [
            key for key, (ts, _, _) in self._cache.items() if now - ts >= self.ttl
        ]
        for key in expired_keys:
            del self._cache[key]
        if expired_keys:
            logger.debug("Cleaned up %d expired idempotency entries", len(expired_keys))

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only apply to POST requests on API endpoints
        if request.method != "POST" or not request.url.path.startswith("/v1/"):
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        # Periodic cleanup of expired entries
        self._request_count += 1
        if self._request_count % _CLEANUP_INTERVAL == 0:
            self._cleanup_expired()

        # Check for cached response - O(1) lookup
        cached = self._cache.get(idempotency_key)
        if cached is not None:
            cached_ts, cached_body, cached_status = cached
            if time.time() - cached_ts < self.ttl:
                # Move to end for LRU ordering
                self._cache.move_to_end(idempotency_key)
                logger.info("Idempotency cache hit for key: %s", idempotency_key[:16])
                return JSONResponse(
                    content=cached_body,
                    status_code=cached_status,
                    headers={"X-Idempotency-Replayed": "true"},
                )
            else:
                # Entry expired, remove it
                del self._cache[idempotency_key]

        # Execute the request
        response = await call_next(request)

        # Cache the response for idempotent replays
        # Note: We can't easily read the response body from a StreamingResponse
        # so we only cache JSON responses
        if hasattr(response, "body"):
            try:
                body = json.loads(response.body.decode())  # type: ignore[union-attr]
                # Evict oldest entry if at capacity
                if len(self._cache) >= _MAX_CACHE_SIZE:
                    self._cache.popitem(last=False)
                self._cache[idempotency_key] = (time.time(), body, response.status_code)
            except (ValueError, TypeError, OSError):
                pass

        return response
