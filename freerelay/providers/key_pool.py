"""
FreeRelay — KeyPool: multi-key round-robin with per-key 429 cooldown.

Generalises the ad-hoc `nvidia_api_key_2` pattern so every provider can
hold multiple API keys and rotate through them automatically.
"""

from __future__ import annotations

import time


class KeyPool:
    """
    Round-robin pool of API keys for a single provider.

    On a 429 response the caller should call ``cooldown(key)`` to park that
    key for ``cooldown_secs`` seconds.  Subsequent ``next()`` calls skip
    cooled-down keys.  If ALL keys are cooled-down, ``next()`` returns the
    one whose cooldown expires soonest (graceful degradation).
    """

    def __init__(self, keys: list[str], cooldown_secs: float = 60.0) -> None:
        if not keys:
            raise ValueError("KeyPool requires at least one key")
        self._keys = list(keys)
        self._cooldown_secs = cooldown_secs
        # key → timestamp when cooldown expires (0 = no cooldown)
        self._cooldown_until: dict[str, float] = {k: 0.0 for k in keys}
        self._index = 0

    # ------------------------------------------------------------------
    def next(self) -> str:
        """Return the next available key (round-robin, skipping cooled-down)."""
        now = time.monotonic()
        n = len(self._keys)

        # Try each slot starting from current index
        for i in range(n):
            idx = (self._index + i) % n
            key = self._keys[idx]
            if now >= self._cooldown_until[key]:
                self._index = (idx + 1) % n
                return key

        # All keys are cooled-down — return whichever expires soonest
        best = min(self._keys, key=lambda k: self._cooldown_until[k])
        self._index = (self._keys.index(best) + 1) % n
        return best

    def cooldown(self, key: str, secs: float | None = None) -> None:
        """Mark *key* as rate-limited for *secs* seconds."""
        duration = secs if secs is not None else self._cooldown_secs
        self._cooldown_until[key] = time.monotonic() + duration

    def all_cooled(self) -> bool:
        """True if every key is currently rate-limited."""
        now = time.monotonic()
        return all(self._cooldown_until[k] > now for k in self._keys)

    @property
    def primary(self) -> str:
        """The first key in the pool (used as a stable identifier in logs)."""
        return self._keys[0]

    @staticmethod
    def from_csv(value: str, cooldown_secs: float = 60.0) -> KeyPool:
        """
        Build a KeyPool from a comma-separated string of keys.

        Empty strings are filtered out so `KEY=sk-abc` (single key) and
        `KEY=sk-abc,sk-def` (two keys) both work.
        """
        keys = [k.strip() for k in value.split(",") if k.strip()]
        if not keys:
            raise ValueError("No valid keys found in CSV string")
        return KeyPool(keys, cooldown_secs=cooldown_secs)

    def __len__(self) -> int:
        return len(self._keys)

    def __repr__(self) -> str:
        return f"KeyPool(n={len(self._keys)}, cooldown={self._cooldown_secs}s)"
