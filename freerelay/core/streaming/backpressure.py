"""
FreeRelay — Streaming Backpressure (§12)
==========================================
Bounded asyncio.Queue between provider (producer) and client (consumer).
Prevents unbounded memory growth when provider produces faster than
client consumes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

logger = logging.getLogger("freerelay.backpressure")

_SENTINEL = None


async def stream_with_backpressure(
    provider_stream: AsyncIterator[str],
    buffer_size: int = 32,
) -> AsyncIterator[str]:
    """
    Buffer a provider stream with backpressure.

    Uses a bounded asyncio.Queue:
    - Producer: reads from provider, puts into queue (blocks if full)
    - Consumer: yields from queue

    If client disconnects, producer task is cancelled to stop
    calling the provider.

    Args:
        provider_stream: Raw SSE lines from a provider.
        buffer_size: Maximum chunks buffered before backpressure kicks in.

    Yields:
        SSE lines with backpressure applied.

    Raises:
        Exception: If the provider stream errors.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=buffer_size)
    producer_error: BaseException | None = None

    async def producer() -> None:
        nonlocal producer_error
        try:
            async for chunk in provider_stream:
                await queue.put(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            producer_error = exc
            logger.warning("Provider stream error: %s", str(exc)[:200])
        finally:
            await queue.put(_SENTINEL)

    producer_task = asyncio.create_task(producer())

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

        # If producer errored, propagate it to the consumer
        if producer_error is not None:
            raise producer_error
    finally:
        producer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer_task
