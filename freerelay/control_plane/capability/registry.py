"""
FreeRelay — Capability Registry
=================================
CRUD operations for provider capability records backed by Redis.
Maintains warm cache with 60s refresh for fast lookups.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

CAPABILITY_KEY_PREFIX = "freerelay:capability"
CACHE_REFRESH_INTERVAL = 60  # seconds


@dataclass
class CapabilityRecord:
    """Live capability record for a provider/model combination."""

    provider: str
    model: str
    context_window: int = 8192
    max_output_tokens: int = 4096
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_logprobs: bool = False
    speed_tier: str = "medium"  # fast | medium | slow
    quality_tier: str = "medium"  # low | medium | high
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    # Live metrics (updated from outcomes)
    p50_ttft_ms: float = 0.0
    p95_ttft_ms: float = 0.0
    p99_ttft_ms: float = 0.0
    schema_compliance_rate: float = 1.0
    quality_by_task_family: dict[str, float] = field(default_factory=dict)
    # Health flags
    latency_degraded: bool = False
    error_rate_degraded: bool = False
    last_degraded_at: float = 0.0
    # Metadata
    last_updated_ts: float = field(default_factory=time.time)
    notes: str = ""

    @property
    def key(self) -> str:
        return f"{CAPABILITY_KEY_PREFIX}:{self.provider}:{self.model}"

    @property
    def is_healthy(self) -> bool:
        return not (self.latency_degraded or self.error_rate_degraded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "context_window": str(self.context_window),
            "max_output_tokens": str(self.max_output_tokens),
            "supports_streaming": str(self.supports_streaming),
            "supports_tools": str(self.supports_tools),
            "supports_vision": str(self.supports_vision),
            "supports_json_mode": str(self.supports_json_mode),
            "supports_logprobs": str(self.supports_logprobs),
            "speed_tier": self.speed_tier,
            "quality_tier": self.quality_tier,
            "cost_per_1k_input": str(self.cost_per_1k_input),
            "cost_per_1k_output": str(self.cost_per_1k_output),
            "p50_ttft_ms": str(self.p50_ttft_ms),
            "p95_ttft_ms": str(self.p95_ttft_ms),
            "p99_ttft_ms": str(self.p99_ttft_ms),
            "schema_compliance_rate": str(self.schema_compliance_rate),
            "quality_by_task_family": json.dumps(self.quality_by_task_family),
            "latency_degraded": str(self.latency_degraded),
            "error_rate_degraded": str(self.error_rate_degraded),
            "last_degraded_at": str(self.last_degraded_at),
            "last_updated_ts": str(self.last_updated_ts),
            "notes": self.notes,
        }

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> CapabilityRecord:
        """Hydrate from Redis hash data."""
        quality_by_task = {}
        raw_quality = data.get("quality_by_task_family", "{}")
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            quality_by_task = json.loads(raw_quality)

        return cls(
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            context_window=int(data.get("context_window", 8192)),
            max_output_tokens=int(data.get("max_output_tokens", 4096)),
            supports_streaming=data.get("supports_streaming", "True") == "True",
            supports_tools=data.get("supports_tools", "False") == "True",
            supports_vision=data.get("supports_vision", "False") == "True",
            supports_json_mode=data.get("supports_json_mode", "False") == "True",
            supports_logprobs=data.get("supports_logprobs", "False") == "True",
            speed_tier=data.get("speed_tier", "medium"),
            quality_tier=data.get("quality_tier", "medium"),
            cost_per_1k_input=float(data.get("cost_per_1k_input", 0)),
            cost_per_1k_output=float(data.get("cost_per_1k_output", 0)),
            p50_ttft_ms=float(data.get("p50_ttft_ms", 0)),
            p95_ttft_ms=float(data.get("p95_ttft_ms", 0)),
            p99_ttft_ms=float(data.get("p99_ttft_ms", 0)),
            schema_compliance_rate=float(data.get("schema_compliance_rate", 1.0)),
            quality_by_task_family=quality_by_task,
            latency_degraded=data.get("latency_degraded", "False") == "True",
            error_rate_degraded=data.get("error_rate_degraded", "False") == "True",
            last_degraded_at=float(data.get("last_degraded_at", 0)),
            last_updated_ts=float(data.get("last_updated_ts", time.time())),
            notes=data.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Default capability records for all 5 providers
# ---------------------------------------------------------------------------

DEFAULT_RECORDS: list[CapabilityRecord] = [
    CapabilityRecord(
        provider="groq",
        model="llama-3.1-70b-versatile",
        context_window=131072,
        max_output_tokens=32768,
        supports_streaming=True,
        supports_tools=True,
        supports_json_mode=True,
        speed_tier="fast",
        quality_tier="high",
        cost_per_1k_input=0.00059,
        cost_per_1k_output=0.00079,
    ),
    CapabilityRecord(
        provider="google",
        model="gemini-2.0-flash",
        context_window=1048576,
        max_output_tokens=8192,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=True,
        supports_json_mode=True,
        speed_tier="fast",
        quality_tier="high",
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0004,
    ),
    CapabilityRecord(
        provider="openrouter",
        model="meta-llama/llama-3.1-70b-instruct",
        context_window=131072,
        max_output_tokens=32768,
        supports_streaming=True,
        supports_tools=True,
        supports_json_mode=True,
        speed_tier="medium",
        quality_tier="high",
        cost_per_1k_input=0.00052,
        cost_per_1k_output=0.00075,
    ),
    CapabilityRecord(
        provider="together",
        model="meta-llama/Llama-3.1-70B-Instruct-Turbo",
        context_window=131072,
        max_output_tokens=32768,
        supports_streaming=True,
        supports_tools=True,
        supports_json_mode=True,
        speed_tier="medium",
        quality_tier="high",
        cost_per_1k_input=0.00088,
        cost_per_1k_output=0.00088,
    ),
    CapabilityRecord(
        provider="mistral",
        model="mistral-large-latest",
        context_window=131072,
        max_output_tokens=32768,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=True,
        supports_json_mode=True,
        speed_tier="medium",
        quality_tier="high",
        cost_per_1k_input=0.002,
        cost_per_1k_output=0.006,
    ),
]


class CapabilityRegistry:
    """
    Manages capability records for all providers.

    Redis keys: freerelay:capability:{provider}:{model}
    Supports warm cache with periodic refresh.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._cache: dict[str, CapabilityRecord] = {}
        self._cache_ts: float = 0.0
        self._refresh_task: asyncio.Task[None] | None = None

    async def initialize_defaults(self) -> None:
        """Seed default records if they don't exist yet."""
        for record in DEFAULT_RECORDS:
            existing = await self.get_record(record.provider, record.model)
            if existing is None:
                await self.update_record(record)
                logger.info(
                    "capability_seeded provider=%s model=%s",
                    record.provider,
                    record.model,
                )

    async def get_record(self, provider: str, model: str) -> CapabilityRecord | None:
        """Load a capability record from Redis."""
        key = f"{CAPABILITY_KEY_PREFIX}:{provider}:{model}"
        try:
            data = await self._redis.hgetall(key)
            if not data:
                return None
            return CapabilityRecord.from_redis(data)
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("get_record_error provider=%s model=%s", provider, model)
            return None

    async def update_record(self, record: CapabilityRecord) -> None:
        """Persist a capability record to Redis."""
        try:
            record.last_updated_ts = time.time()
            await self._redis.hset(record.key, mapping=record.to_dict())
            # Update cache
            cache_key = f"{record.provider}:{record.model}"
            self._cache[cache_key] = record
            logger.debug(
                "capability_updated provider=%s model=%s", record.provider, record.model
            )
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception(
                "update_record_error provider=%s model=%s",
                record.provider,
                record.model,
            )

    async def list_records(self, provider: str | None = None) -> list[CapabilityRecord]:
        """List all capability records, optionally filtered by provider."""
        try:
            pattern = f"{CAPABILITY_KEY_PREFIX}:"
            if provider:
                pattern += f"{provider}:"
            pattern += "*"

            records: list[CapabilityRecord] = []
            async for key in self._redis.scan_iter(match=pattern, count=200):
                data = await self._redis.hgetall(key)
                if data:
                    records.append(CapabilityRecord.from_redis(data))
            return records
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("list_records_error")
            return []

    async def delete_record(self, provider: str, model: str) -> bool:
        """Delete a capability record."""
        key = f"{CAPABILITY_KEY_PREFIX}:{provider}:{model}"
        try:
            deleted = await self._redis.delete(key)
            cache_key = f"{provider}:{model}"
            self._cache.pop(cache_key, None)
            if deleted:
                logger.info("capability_deleted provider=%s model=%s", provider, model)
            return bool(deleted)
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception(
                "delete_record_error provider=%s model=%s", provider, model
            )
            return False

    async def get_cached(self, provider: str, model: str) -> CapabilityRecord | None:
        """Get from warm cache, refreshing if stale."""
        now = time.time()
        cache_key = f"{provider}:{model}"

        if (
            now - self._cache_ts > CACHE_REFRESH_INTERVAL
            or cache_key not in self._cache
        ):
            record = await self.get_record(provider, model)
            if record:
                self._cache[cache_key] = record
                self._cache_ts = now
            return record

        return self._cache.get(cache_key)

    async def refresh_cache(self) -> None:
        """Force refresh of the warm cache."""
        records = await self.list_records()
        self._cache = {f"{r.provider}:{r.model}": r for r in records}
        self._cache_ts = time.time()
        logger.info("capability_cache_refreshed count=%d", len(self._cache))

    def start_background_refresh(self) -> None:
        """Start background task that refreshes cache every 60s."""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._background_refresh_loop())

    def stop_background_refresh(self) -> None:
        """Stop background cache refresh."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

    async def _background_refresh_loop(self) -> None:
        """Background loop for cache refresh."""
        while True:
            try:
                await asyncio.sleep(CACHE_REFRESH_INTERVAL)
                await self.refresh_cache()
            except asyncio.CancelledError:
                break
            except (redis.ConnectionError, redis.ResponseError):
                logger.exception("cache_refresh_error")
                await asyncio.sleep(CACHE_REFRESH_INTERVAL)

    async def get_healthy_providers(self) -> list[CapabilityRecord]:
        """Return only providers without degradation flags."""
        all_records = await self.list_records()
        return [r for r in all_records if r.is_healthy]

    async def set_degradation(
        self,
        provider: str,
        model: str,
        field: str,
        value: bool,
    ) -> None:
        """Set a specific degradation flag on a capability record."""
        key = f"{CAPABILITY_KEY_PREFIX}:{provider}:{model}"
        try:
            await self._redis.hset(key, field, str(value))
            if value:
                await self._redis.hset(key, "last_degraded_at", str(time.time()))
            # Invalidate cache
            cache_key = f"{provider}:{model}"
            self._cache.pop(cache_key, None)
            logger.info(
                "capability_degradation provider=%s model=%s field=%s value=%s",
                provider,
                model,
                field,
                value,
            )
        except (redis.ConnectionError, redis.ResponseError):
            logger.exception("set_degradation_error")
