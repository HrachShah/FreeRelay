"""
FreeRelay — SessionAffinity: pin conversations to a provider.

A sticky session ensures that follow-up messages in a multi-turn
conversation keep landing on the same provider, improving coherence and
avoiding context-reset surprises.

Session ID resolution order:
  1. ``X-Session-Id`` request header (passed in from the caller)
  2. ``request.user`` field (OpenAI standard)
  3. Hash of the first two messages (stable across retries)

The affinity entry expires after *ttl_secs* of inactivity (default 30 min).
When the affined provider's circuit breaker is OPEN the entry is cleared and
routing falls back to normal scoring.
"""

from __future__ import annotations

import hashlib
import time


class SessionAffinity:
    """
    In-memory sticky-session map.

    Stores ``session_id → (provider_name, expires_at)`` pairs and evicts
    stale entries lazily on every lookup.
    """

    def __init__(self, ttl_secs: float = 1800.0) -> None:
        self._ttl = ttl_secs
        # session_id -> (provider_name, expires_at)
        self._store: dict[str, tuple[str, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> str | None:
        """Return the affinied provider name, or None if missing/expired."""
        entry = self._store.get(session_id)
        if entry is None:
            return None
        provider, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[session_id]
            return None
        return provider

    def pin(self, session_id: str, provider_name: str) -> None:
        """Associate *session_id* with *provider_name* (resets TTL)."""
        self._store[session_id] = (provider_name, time.monotonic() + self._ttl)

    def clear(self, session_id: str) -> None:
        """Remove affinity for *session_id* (e.g. provider circuit opened)."""
        self._store.pop(session_id, None)

    def evict_expired(self) -> int:
        """Prune stale entries; returns the number removed."""
        now = time.monotonic()
        stale = [sid for sid, (_, exp) in self._store.items() if now > exp]
        for sid in stale:
            del self._store[sid]
        return len(stale)

    def __len__(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Session ID helpers
    # ------------------------------------------------------------------

    @staticmethod
    def derive_session_id(
        *,
        header: str | None = None,
        user_field: str | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> str | None:
        """
        Resolve a session ID from the available sources.

        Returns None if no stable identifier can be derived (single-turn,
        no header, no user field, no messages).
        """
        if header:
            return header
        if user_field:
            return user_field
        if messages and len(messages) >= 2:
            # Hash first two messages for a stable conversation fingerprint
            payload = repr(messages[:2]).encode()
            return "conv-" + hashlib.sha256(payload).hexdigest()[:16]
        return None
