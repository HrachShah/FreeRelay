"""
FreeRelay — Shared HTTP Client Manager
========================================
Provides a singleton async HTTP client with connection pooling and HTTP/2 support.
All providers share this client to avoid creating new connections per request.
"""

from __future__ import annotations

import httpx
import logging

logger = logging.getLogger("freerelay.http_client")

# Connection pool settings
_MAX_CONNECTIONS = 100
_MAX_KEEPALIVE_CONNECTIONS = 20
_KEEPALIVE_EXPIRY = 30.0  # seconds
_HTTP2 = True  # Enable HTTP/2 for multiplexing

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """
    Get the shared HTTP client instance.
    Creates it lazily on first use with optimal connection pooling.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=_MAX_CONNECTIONS,
                max_keepalive_connections=_MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=_KEEPALIVE_EXPIRY,
            ),
            http2=_HTTP2,
            follow_redirects=True,
        )
        logger.info(
            "HTTP client initialized: max_conn=%d, keepalive=%d, http2=%s",
            _MAX_CONNECTIONS,
            _MAX_KEEPALIVE_CONNECTIONS,
            _HTTP2,
        )
    return _client


async def close_client() -> None:
    """Close the shared HTTP client and release all connections."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        logger.info("HTTP client closed")
        _client = None
