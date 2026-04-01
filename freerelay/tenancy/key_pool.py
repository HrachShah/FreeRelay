"""
FreeRelay — Per-Namespace API Key Pooling
============================================
Manages multiple API keys per provider per namespace.
Round-robin selection with automatic failover.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass

logger = logging.getLogger("freerelay.key_pool")


@dataclass
class APIKeyEntry:
    """A single API key with metadata."""

    key: str
    is_active: bool = True
    error_count: int = 0
    last_error_ts: float = 0.0


class KeyPool:
    """
    API key pool for a single provider.

    Supports round-robin selection and automatic failover
    when a key hits rate limits or errors.
    """

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self._keys: list[APIKeyEntry] = []
        self._round_robin: itertools.cycle[APIKeyEntry] | None = None

    def add_key(self, key: str) -> None:
        """Add an API key to the pool."""
        self._keys.append(APIKeyEntry(key=key))
        self._round_robin = itertools.cycle(self._keys)

    def get_key(self) -> str:
        """
        Get the next API key via round-robin.

        Returns:
            API key string.

        Raises:
            RuntimeError: If no keys are available.
        """
        if not self._keys:
            raise RuntimeError(f"No API keys configured for {self.provider_name}")

        if self._round_robin is None:
            self._round_robin = itertools.cycle(self._keys)

        # Try up to len(keys) times to find an active key
        for _ in range(len(self._keys)):
            entry = next(self._round_robin)
            if entry.is_active:
                return entry.key

        # All keys inactive, reset and return first
        logger.warning("All keys inactive for %s, using first key", self.provider_name)
        self._keys[0].is_active = True
        return self._keys[0].key

    def report_error(self, key: str) -> None:
        """Report an error for a key (for future deactivation logic)."""
        for entry in self._keys:
            if entry.key == key:
                entry.error_count += 1
                break

    def report_success(self, key: str) -> None:
        """Report a success for a key."""
        for entry in self._keys:
            if entry.key == key:
                entry.error_count = max(0, entry.error_count - 1)
                break

    @property
    def key_count(self) -> int:
        """Number of keys in the pool."""
        return len(self._keys)


class KeyPoolManager:
    """Manages key pools across all providers and namespaces."""

    def __init__(self) -> None:
        self._pools: dict[str, KeyPool] = {}  # "{namespace}:{provider}" → KeyPool

    def _pool_key(self, namespace: str, provider: str) -> str:
        return f"{namespace}:{provider}"

    def get_pool(self, namespace: str, provider: str) -> KeyPool:
        """Get or create a key pool for a namespace+provider."""
        pk = self._pool_key(namespace, provider)
        if pk not in self._pools:
            self._pools[pk] = KeyPool(provider)
        return self._pools[pk]

    def add_key(self, namespace: str, provider: str, key: str) -> None:
        """Add a key to a namespace+provider pool."""
        pool = self.get_pool(namespace, provider)
        pool.add_key(key)

    def get_key(self, namespace: str, provider: str) -> str:
        """Get the next key for a namespace+provider."""
        pool = self.get_pool(namespace, provider)
        return pool.get_key()
