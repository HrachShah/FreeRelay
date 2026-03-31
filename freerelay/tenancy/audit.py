"""
FreeRelay — Per-Tenant Audit Log
===================================
Namespace-scoped audit trail for compliance and debugging.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("freerelay.tenancy_audit")


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: float
    namespace: str
    request_id: str
    method: str
    path: str
    status_code: int
    latency_ms: float
    provider: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0


class TenantAuditLog:
    """
    Per-tenant audit log.

    In production, entries are persisted to a database or log aggregator.
    For now, uses in-memory storage with a max size.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self.max_entries = max_entries
        self._entries: list[AuditEntry] = []

    def log(self, entry: AuditEntry) -> None:
        """Add an audit entry."""
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def get_entries(
        self,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """
        Get audit entries, optionally filtered by namespace.

        Args:
            namespace: Filter by namespace (None = all).
            limit: Maximum entries to return.

        Returns:
            List of audit entries (newest first).
        """
        entries = self._entries
        if namespace:
            entries = [e for e in entries if e.namespace == namespace]
        return list(reversed(entries[-limit:]))

    def get_stats(self, namespace: str | None = None) -> dict[str, object]:
        """Get audit statistics."""
        entries = self._entries
        if namespace:
            entries = [e for e in entries if e.namespace == namespace]

        if not entries:
            return {"total_requests": 0}

        total_latency = sum(e.latency_ms for e in entries)
        total_tokens = sum(e.tokens_prompt + e.tokens_completion for e in entries)
        errors = sum(1 for e in entries if e.status_code >= 400)

        return {
            "total_requests": len(entries),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(total_latency / len(entries), 1),
            "error_count": errors,
            "error_rate": round(errors / len(entries), 3) if entries else 0,
        }
