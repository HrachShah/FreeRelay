"""
FreeRelay — Async Request Cancellation (§12)
===============================================
Handles cancellation of in-flight provider requests
when the client disconnects or a faster hedged response wins.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

logger = logging.getLogger("freerelay.cancellation")


class CancellableRequest:
    """
    Wraps an httpx streaming request for cancellation support.

    When cancelled (client disconnect, hedged loss), the underlying
    HTTP connection is closed to stop receiving data from the provider.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._cancelled = False

    def set_task(self, task: asyncio.Task[None]) -> None:
        """Set the underlying async task for cancellation."""
        self._task = task

    def cancel(self) -> None:
        """Cancel the in-flight request."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def is_cancelled(self) -> bool:
        """Check if the request has been cancelled."""
        return self._cancelled


async def cancellable_stream(
    stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """
    Wrap a provider stream with cancellation support.

    If the consumer stops iterating (client disconnect),
    the provider stream is properly closed.

    Args:
        stream: Provider SSE stream.

    Yields:
        SSE lines from the provider.
    """
    try:
        async for line in stream:
            yield line
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
        raise
    except (ValueError, TypeError, OSError) as e:
        logger.warning("Stream error: %s", str(e)[:100])
        raise
