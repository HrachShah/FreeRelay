"""
FreeRelay — Signed Audit Trail (§14.2)
========================================
Namespace-scoped, tamper-evident audit log with HMAC-SHA256 signatures.
Supports Redis stream storage with configurable retention.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from freerelay.shared.models.internal import AuditRecord
from freerelay.shared.security.crypto import sign_audit_record, verify_audit_record

logger = logging.getLogger("freerelay.shared.tenancy.audit")


# ─── Audit Logger ────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Append-only, HMAC-signed audit trail per namespace.

    Storage backends:
      - In-memory (default, for dev/testing)
      - Redis streams (production, key pattern: freerelay:audit:{namespace})

    Each record is signed with a per-tenant secret to detect tampering.
    """

    def __init__(
        self,
        tenant_secret: str,
        redis_url: str | None = None,
        retention_seconds: int = 86400 * 30,  # 30 days default
    ) -> None:
        """
        Args:
            tenant_secret: Per-tenant HMAC secret for signing audit records.
            redis_url: Redis connection URL (None = in-memory storage).
            retention_seconds: How long to retain audit records.
        """
        self._tenant_secret = tenant_secret
        self._retention_seconds = retention_seconds
        self._redis_url = redis_url
        self._redis: Any = None

        # In-memory fallback
        self._memory_store: dict[str, list[dict[str, Any]]] = {}

    async def _get_redis(self) -> Any:
        """Lazily connect to Redis."""
        if self._redis is None and self._redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                )
                logger.info("Audit logger connected to Redis")
            except ImportError:
                logger.warning(
                    "redis package not installed — falling back to in-memory audit storage"
                )
        return self._redis

    def _stream_key(self, namespace: str) -> str:
        """Redis stream key for a namespace."""
        return f"freerelay:audit:{namespace}"

    # ── Core Operations ──────────────────────────────────────────────────────

    async def log_request(
        self,
        namespace: str,
        request_id: str,
        provider_called: str,
        prompt_hash: str = "",
        response_hash: str = "",
        pii_fields_masked: list[str] | None = None,
        routing_decision_hash: str = "",
    ) -> AuditRecord:
        """
        Create and store a signed audit record.

        Args:
            namespace: Tenant namespace.
            request_id: Request identifier.
            provider_called: Provider that handled the request.
            prompt_hash: SHA-256 hash of the prompt (for correlation, not content).
            response_hash: SHA-256 hash of the response.
            pii_fields_masked: List of PII types that were masked.
            routing_decision_hash: Hash of the routing decision.

        Returns:
            The signed AuditRecord.
        """
        record = AuditRecord(
            record_id=f"aud_{uuid.uuid4().hex[:16]}",
            timestamp_utc=time.time(),
            namespace=namespace,
            request_id=request_id,
            provider_called=provider_called,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
            pii_fields_masked=pii_fields_masked or [],
            routing_decision_hash=routing_decision_hash,
        )

        # Sign the record (exclude signature field itself)
        signable_fields = {
            "record_id": record.record_id,
            "timestamp_utc": record.timestamp_utc,
            "namespace": record.namespace,
            "request_id": record.request_id,
            "provider_called": record.provider_called,
            "prompt_hash": record.prompt_hash,
            "response_hash": record.response_hash,
            "pii_fields_masked": record.pii_fields_masked,
            "routing_decision_hash": record.routing_decision_hash,
        }
        record.signature = sign_audit_record(signable_fields, self._tenant_secret)

        # Persist
        await self._persist(namespace, record)

        logger.debug(
            "Audit record created",
            extra={
                "record_id": record.record_id,
                "namespace": namespace,
                "request_id": request_id,
            },
        )

        return record

    async def verify_record(self, record: AuditRecord) -> bool:
        """
        Verify an audit record's HMAC signature.

        Args:
            record: The AuditRecord to verify.

        Returns:
            True if the signature is valid, False if tampered.
        """
        signable_fields = {
            "record_id": record.record_id,
            "timestamp_utc": record.timestamp_utc,
            "namespace": record.namespace,
            "request_id": record.request_id,
            "provider_called": record.provider_called,
            "prompt_hash": record.prompt_hash,
            "response_hash": record.response_hash,
            "pii_fields_masked": record.pii_fields_masked,
            "routing_decision_hash": record.routing_decision_hash,
        }
        return verify_audit_record(signable_fields, self._tenant_secret, record.signature)

    async def get_audit_trail(
        self,
        namespace: str,
        start_ts: float = 0.0,
        end_ts: float = 0.0,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """
        Retrieve audit records for a namespace within a time range.

        Args:
            namespace: Tenant namespace.
            start_ts: Start timestamp (inclusive, 0 = from beginning).
            end_ts: End timestamp (inclusive, 0 = until now).
            limit: Maximum records to return.

        Returns:
            List of AuditRecords (newest first).
        """
        if end_ts <= 0:
            end_ts = time.time()

        redis = await self._get_redis()
        if redis:
            return await self._get_from_redis(namespace, start_ts, end_ts, limit)
        return self._get_from_memory(namespace, start_ts, end_ts, limit)

    async def purge_expired(self, namespace: str) -> int:
        """
        Purge audit records older than retention period.

        Args:
            namespace: Tenant namespace.

        Returns:
            Number of records purged.
        """
        cutoff = time.time() - self._retention_seconds
        redis = await self._get_redis()

        if redis:
            stream_key = self._stream_key(namespace)
            # Redis XTRIM with MINID strategy
            try:
                # Get entries older than cutoff
                entries = await redis.xrange(
                    stream_key,
                    min="-",
                    max=f"{int(cutoff * 1000)}-0",
                )
                if entries:
                    ids = [e[0] for e in entries]
                    await redis.xdel(stream_key, *ids)
                    logger.info(
                        "Purged %d expired audit records from %s",
                        len(ids),
                        namespace,
                    )
                    return len(ids)
            except OSError as exc:
                logger.error("Failed to purge audit records: %s", exc)
            return 0

        # In-memory purge
        records = self._memory_store.get(namespace, [])
        before = len(records)
        self._memory_store[namespace] = [
            r for r in records if r.get("timestamp_utc", 0) >= cutoff
        ]
        purged = before - len(self._memory_store[namespace])
        if purged:
            logger.info("Purged %d expired audit records from memory", purged)
        return purged

    # ── Persistence Layer ────────────────────────────────────────────────────

    async def _persist(self, namespace: str, record: AuditRecord) -> None:
        """Write audit record to Redis or in-memory store."""
        redis = await self._get_redis()
        data = record.model_dump_json()

        if redis:
            stream_key = self._stream_key(namespace)
            try:
                await redis.xadd(
                    stream_key,
                    {"data": data},
                    maxlen=100_000,  # Cap stream size
                )
                return
            except OSError as exc:
                logger.error("Redis audit write failed, falling back to memory: %s", exc)

        # In-memory fallback
        if namespace not in self._memory_store:
            self._memory_store[namespace] = []
        self._memory_store[namespace].append(record.model_dump())

    async def _get_from_redis(
        self,
        namespace: str,
        start_ts: float,
        end_ts: float,
        limit: int,
    ) -> list[AuditRecord]:
        """Read audit records from Redis stream."""
        stream_key = self._stream_key(namespace)
        redis = await self._get_redis()

        try:
            entries = await redis.xrange(
                stream_key,
                min=f"{int(start_ts * 1000)}-0" if start_ts > 0 else "-",
                max=f"{int(end_ts * 1000)}-0",
                count=limit,
            )
            records: list[AuditRecord] = []
            for _, fields in entries:
                try:
                    data = json.loads(fields["data"])
                    records.append(AuditRecord(**data))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Corrupt audit record in Redis: %s", exc)

            # Return newest first
            records.reverse()
            return records
        except OSError as exc:
            logger.error("Redis audit read failed: %s", exc)
            return []

    def _get_from_memory(
        self,
        namespace: str,
        start_ts: float,
        end_ts: float,
        limit: int,
    ) -> list[AuditRecord]:
        """Read audit records from in-memory store."""
        records = self._memory_store.get(namespace, [])
        filtered = [
            AuditRecord(**r)
            for r in records
            if start_ts <= r.get("timestamp_utc", 0) <= end_ts
        ]
        # Return newest first, limited
        return list(reversed(filtered))[:limit]
