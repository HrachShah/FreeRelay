"""
FreeRelay — Circuit Breaker (§9)
==================================
CLOSED → OPEN → HALF_OPEN state machine.
Each provider has its own independent instance.

States:
  CLOSED:    Normal operation, requests flow through.
  OPEN:      Provider failing, all requests rejected immediately.
  HALF_OPEN: Probe state, one request allowed to test recovery.

Transition Rules:
  CLOSED → OPEN:      failure_count >= FAILURE_THRESHOLD within FAILURE_WINDOW
  OPEN → HALF_OPEN:   RECOVERY_TIMEOUT seconds elapsed
  HALF_OPEN → CLOSED: probe request succeeds
  HALF_OPEN → OPEN:   probe request fails → reset timer

What counts as failure (§9.3):
  429, 500, 502, 503, 504, timeout, connect error → YES
  400, 401, 403 → NO (client error)
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# HTTP status codes that count as provider failures
_FAILURE_STATUS_CODES = {429, 500, 502, 503, 504}


class CircuitBreaker:
    """
    In-memory circuit breaker for a single provider.

    Thread-safe via asyncio.Lock.
    For Redis-backed version, see the redis integration module.
    """

    __slots__ = (
        "provider_name",
        "failure_threshold",
        "failure_window",
        "recovery_timeout",
        "_state",
        "_failure_timestamps",
        "_open_since",
        "_lock",
    )

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        failure_window: int = 60,
        recovery_timeout: int = 30,
    ) -> None:
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._open_since: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state, checking for auto-transition OPEN → HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._open_since >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    async def can_execute(self) -> bool:
        """
        Check if a request is allowed through.

        Returns:
            True if the circuit allows the request.
        """
        async with self._lock:
            current = self.state

            if current == CircuitState.CLOSED:
                return True

            if current == CircuitState.HALF_OPEN:
                return True  # Allow one probe request

            # OPEN
            return False

    async def record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_timestamps.clear()

    async def record_failure(self, status_code: int | None = None) -> None:
        """
        Record a failed request.

        Args:
            status_code: HTTP status code, or None for connection/timeout errors.
        """
        # Client errors don't count as failures (§9.3)
        if status_code is not None and status_code not in _FAILURE_STATUS_CODES:
            return

        async with self._lock:
            now = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed → back to OPEN
                self._state = CircuitState.OPEN
                self._open_since = now
                return

            # CLOSED state — track failures
            self._failure_timestamps.append(now)

            # Prune old failures outside the window - use in-place filter
            cutoff = now - self.failure_window
            # Efficiently remove old entries without creating a new list
            write_idx = 0
            for read_idx, ts in enumerate(self._failure_timestamps):
                if ts > cutoff:
                    self._failure_timestamps[write_idx] = ts
                    write_idx += 1
            del self._failure_timestamps[write_idx:]

            if len(self._failure_timestamps) >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._open_since = now

    def get_score(self) -> float:
        """
        Score for routing engine (§14.1).
        CLOSED = 1.0, HALF_OPEN = 0.5, OPEN = 0.0
        """
        current = self.state
        if current == CircuitState.CLOSED:
            return 1.0
        if current == CircuitState.HALF_OPEN:
            return 0.5
        return 0.0

    def to_dict(self) -> dict[str, object]:
        """State for dashboard/API."""
        return {
            "provider": self.provider_name,
            "state": self.state.value,
            "failure_count": len(self._failure_timestamps),
            "score": self.get_score(),
        }
