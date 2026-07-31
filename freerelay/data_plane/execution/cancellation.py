"""
FreeRelay Data Plane — Request Cancellation (§8.4)
=====================================================
Cancellable request wrapper for httpx with async-safe lifecycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger("freerelay.data_plane.cancellation")


class CancellationReason(StrEnum):
    """Reasons for request cancellation."""

    TIMEOUT = "timeout"
    CLIENT_DISCONNECT = "client_disconnect"
    MANUAL = "manual"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXHAUSTED = "budget_exhausted"
    REPLACED = "replaced"  # Hedged request won by another


@dataclass
class CancellationState:
    """State of a cancellable request."""

    request_id: str
    cancelled: bool = False
    reason: CancellationReason | None = None
    cancelled_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class CancellableRequest:
    """
    Async-safe wrapper for managing request cancellation.

    Wraps httpx request lifecycle with:
      - asyncio.Event for cancellation signaling
      - Reason tracking for audit logs
      - Timeout enforcement
      - httpx client cancellation

    Usage:
        async with CancellableRequest("req_123", timeout=30.0) as req:
            if req.is_cancelled:
                return
            response = await client.send(req.prepare(...))
    """

    def __init__(
        self,
        request_id: str,
        timeout: float = 60.0,
        httpx_client: Any | None = None,
    ) -> None:
        self._state = CancellationState(request_id=request_id)
        self._cancel_event = asyncio.Event()
        self._timeout = timeout
        self._httpx_client = httpx_client
        self._httpx_request: Any | None = None
        self._timeout_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def request_id(self) -> str:
        return self._state.request_id

    @property
    def is_cancelled(self) -> bool:
        return self._state.cancelled

    @property
    def state(self) -> CancellationState:
        return self._state

    async def cancel(
        self, reason: CancellationReason = CancellationReason.MANUAL
    ) -> None:
        """
        Cancel the request.

        Args:
            reason: Why the request was cancelled.
        """
        async with self._lock:
            if self._state.cancelled:
                return

            self._state.cancelled = True
            self._state.reason = reason
            self._state.cancelled_at = time.time()

            logger.info(
                "Request %s cancelled: %s",
                self._state.request_id,
                reason.value,
            )

            # Signal waiters
            self._cancel_event.set()

            # Cancel httpx request if active
            if self._httpx_request is not None and self._httpx_client is not None:
                try:
                    await self._httpx_client.cancel_request(self._httpx_request)
                except (OSError, httpx.RequestError) as err:
                    logger.debug(
                        "Failed to cancel httpx request %s: %s",
                        self._state.request_id,
                        err,
                    )

            # Cancel timeout task
            if self._timeout_task is not None and not self._timeout_task.done():
                self._timeout_task.cancel()

    async def wait_for_cancellation(self) -> bool:
        """
        Wait for the request to be cancelled.

        Returns:
            True if cancelled, False if timeout reached.
        """
        try:
            async with asyncio.timeout(self._timeout):
                await self._cancel_event.wait()
                return True
        except TimeoutError:
            await self.cancel(CancellationReason.TIMEOUT)
            return True

    async def __aenter__(self) -> CancellableRequest:
        # Start timeout monitor
        self._timeout_task = asyncio.create_task(self._timeout_monitor())
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timeout_task

    async def _timeout_monitor(self) -> None:
        """Background task to enforce timeout."""
        try:
            await asyncio.sleep(self._timeout)
            if not self._state.cancelled:
                await self.cancel(CancellationReason.TIMEOUT)
        except asyncio.CancelledError:
            pass
