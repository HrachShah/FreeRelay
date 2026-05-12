"""
FreeRelay — Outcome Consumer
=============================
Redis XREADGROUP consumer for outcome records emitted by the data plane.
Consumes from the freerelay:outcomes stream with consumer group management.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis
import redis.exceptions
import asyncio

logger = logging.getLogger(__name__)

OUTCOME_STREAM = "freerelay:outcomes"
CONSUMER_GROUP = "control-plane-learner"
DEFAULT_BATCH_SIZE = 100
DEFAULT_BLOCK_MS = 2000


@dataclass
class OutcomeRecord:
    """Parsed outcome record from Redis Stream."""

    message_id: str
    request_id: str = ""
    provider_chosen: str = ""
    model_chosen: str = ""
    task_family: str = "general"
    output_valid: float = 0.0
    judge_score: float = 0.5
    repair_triggered: float = 0.0
    client_retried: float = 0.0
    client_regenerated: float = 0.0
    latency_ms: float = 0.0
    ttft_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    schema_valid: bool | None = None
    timestamp: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_stream(cls, message_id: str, fields: dict[str, str]) -> OutcomeRecord:
        """
        Parse a Redis Stream entry into an OutcomeRecord.
        Handles missing or malformed fields gracefully.
        """
        try:
            return cls(
                message_id=message_id,
                request_id=fields.get("request_id", ""),
                provider_chosen=fields.get("provider_chosen", ""),
                model_chosen=fields.get("model_chosen", ""),
                task_family=fields.get("task_family", "general"),
                output_valid=float(fields.get("output_valid", 0)),
                judge_score=float(fields.get("judge_score", 0.5)),
                repair_triggered=float(fields.get("repair_triggered", 0)),
                client_retried=float(fields.get("client_retried", 0)),
                client_regenerated=float(fields.get("client_regenerated", 0)),
                latency_ms=float(fields.get("latency_ms", 0)),
                ttft_ms=float(fields.get("ttft_ms", 0)),
                tokens_in=int(fields.get("tokens_in", 0)),
                tokens_out=int(fields.get("tokens_out", 0)),
                schema_valid=_parse_optional_bool(fields.get("schema_valid")),
                timestamp=float(fields.get("timestamp", time.time())),
                raw=dict(fields),
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "malformed_outcome_record id=%s error=%s fields=%s",
                message_id,
                exc,
                fields,
            )
            return cls(
                message_id=message_id,
                raw=dict(fields),
            )


def _parse_optional_bool(value: str | None) -> bool | None:
    """Parse a string to optional bool, returning None for missing/unparseable."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return None


class OutcomeConsumer:
    """
    Consumes outcome records from the Redis Stream using consumer groups.

    Usage:
        consumer = OutcomeConsumer(redis_client)
        records = await consumer.consume_batch()
        # process records...
        await consumer.acknowledge([r.message_id for r in records])
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        stream: str = OUTCOME_STREAM,
        group: str = CONSUMER_GROUP,
        consumer_name: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._stream = stream
        self._group = group
        self._consumer_name = consumer_name or f"cp-{id(self):x}"
        self._group_ready = False

    async def ensure_group(self) -> None:
        """
        Create the consumer group if it doesn't exist.
        Uses MKSTREAM to auto-create the stream on first use.
        """
        if self._group_ready:
            return
        try:
            await self._redis.xgroup_create(
                name=self._stream,
                groupname=self._group,
                id="0",
                mkstream=True,
            )
            logger.info(
                "consumer_group_created stream=%s group=%s", self._stream, self._group
            )
        except redis.exceptions.BusyLoadingError:
            logger.debug(
                "consumer_group_not_ready stream=%s group=%s",
                self._stream,
                self._group,
            )
            raise
        except redis.exceptions.GroupNotEmptyError:
            logger.debug(
                "consumer_group_exists stream=%s group=%s",
                self._stream,
                self._group,
            )
        except redis.exceptions.RedisError:
            logger.exception("consumer_group_create_error")
            raise
        except (OSError, asyncio.CancelledError):
            # Catch socket-level errors and cancellation as a last resort
            logger.exception("consumer_group_create_error")
            raise
        self._group_ready = True

    async def consume_batch(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        block_ms: int = DEFAULT_BLOCK_MS,
    ) -> list[OutcomeRecord]:
        """
        Read a batch of outcome records from the stream.
        Returns parsed OutcomeRecord list. Empty on timeout or error.
        """
        await self.ensure_group()
        try:
            results = await self._redis.xreadgroup(
                groupname=self._group,
                consumername=self._consumer_name,
                streams={self._stream: ">"},
                count=batch_size,
                block=block_ms,
            )
        except redis.asyncio.RedisError:
            logger.exception("consume_batch_read_error")
            return []

        records: list[OutcomeRecord] = []
        for _stream_name, messages in results:
            for msg_id, fields in messages:
                try:
                    record = OutcomeRecord.from_stream(msg_id, fields)
                    records.append(record)
                except (ValueError, TypeError):
                    logger.exception("consume_batch_parse_error id=%s", msg_id)

        if records:
            logger.info("consumed_outcomes count=%d", len(records))
        return records

    async def acknowledge(self, message_ids: list[str]) -> int:
        """
        Acknowledge processed messages.
        Returns number of messages acked.
        """
        if not message_ids:
            return 0
        try:
            count = await self._redis.xack(self._stream, self._group, *message_ids)
            logger.debug("acked_outcomes count=%d", count)
            return count
        except redis.asyncio.RedisError:
            logger.exception("acknowledge_error")
            return 0

    async def consume_and_ack(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        block_ms: int = DEFAULT_BLOCK_MS,
    ) -> list[OutcomeRecord]:
        """
        Convenience method: consume a batch and auto-ack all messages.
        Returns parsed records.
        """
        records = await self.consume_batch(batch_size=batch_size, block_ms=block_ms)
        if records:
            await self.acknowledge([r.message_id for r in records])
        return records

    async def pending_info(self) -> dict[str, Any]:
        """Return XPENDING summary for the consumer group."""
        await self.ensure_group()
        try:
            info = await self._redis.xpending(self._stream, self._group)
            return {
                "pending_count": info.get("pending", 0),
                "min_id": info.get("min"),
                "max_id": info.get("max"),
                "consumers": info.get("consumers", []),
            }
        except Exception:
            logger.exception("pending_info_error")
            return {"pending_count": 0}

    async def claim_stale(
        self,
        min_idle_ms: int = 60_000,
        batch_size: int = 50,
    ) -> list[OutcomeRecord]:
        """
        Claim messages that have been idle longer than min_idle_ms.
        Useful for handling crashed consumers.
        """
        await self.ensure_group()
        try:
            pending = await self._redis.xpending_range(
                self._stream,
                self._group,
                min="-",
                max="+",
                count=batch_size,
            )
            if not pending:
                return []

            stale_ids = [
                p["message_id"]
                for p in pending
                if p.get("time_since_delivered", 0) >= min_idle_ms
            ]
            if not stale_ids:
                return []

            claimed = await self._redis.xclaim(
                self._stream,
                self._group,
                self._consumer_name,
                min_idle_ms,
                *stale_ids,
            )

            records: list[OutcomeRecord] = []
            for msg_id, fields in claimed:
                record = OutcomeRecord.from_stream(msg_id, fields)
                records.append(record)

            if records:
                logger.info("claimed_stale_outcomes count=%d", len(records))
            return records

        except Exception:
            logger.exception("claim_stale_error")
            return []
