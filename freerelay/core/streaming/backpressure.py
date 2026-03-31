"""
FreeRelay — Streaming Backpressure (§12)
==========================================
Bounded asyncio.Queue between provider (producer) and client (consumer).
Prevents unbounded memory growth when provider produces faster than client consumes.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


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
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=buffer_size)

    async def producer() -> None:
        try:
            async for chunk in provider_stream:
                await queue.put(chunk)
        except asyncio.CancelledError:
            pass
        finally:
            await queue.put(None)  # Sentinel: stream done

    producer_task = asyncio.create_task(producer())

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
    finally:
        producer_task.cancel()
        try:
            await producer_task
        except asyncio.CancelledError:
            pass
