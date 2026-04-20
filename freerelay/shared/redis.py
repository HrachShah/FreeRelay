"""
FreeRelay — Shared Redis Client
================================
Supports single instance, cluster, and managed solutions (e.g. Upstash).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import redis.asyncio as redis
from redis.asyncio.cluster import RedisCluster

from freerelay.config.settings import Settings

logger = logging.getLogger("freerelay.redis")

_client: Optional[Any] = None

def get_redis_client(settings: Settings) -> Any:
    """Get or create the global Redis client."""
    global _client
    if _client is not None:
        return _client

    if not settings.enable_redis:
        return None

    try:
        # Check if we should use cluster mode
        # We'll use a heuristic: if multiple URLs are provided or explicitly configured
        use_cluster = getattr(settings, "redis_use_cluster", False)
        
        if use_cluster:
            logger.info("Initializing Redis Cluster client")
            _client = RedisCluster.from_url(settings.redis_url, decode_responses=True)
        else:
            logger.info("Initializing Redis client (single instance)")
            _client = redis.from_url(settings.redis_url, decode_responses=True)
            
        return _client
    except Exception:
        logger.exception("Failed to initialize Redis client")
        return None

async def close_redis() -> None:
    """Close the global Redis client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
