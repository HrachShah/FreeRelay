"""
FreeRelay — SSE Proxy Handler (§12)
======================================
Handles Server-Sent Events streaming from provider to client.
Manages SSE event parsing and forwarding.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionChunk,
    DeltaMessage,
    StreamChoice,
)

logger = logging.getLogger("freerelay.sse")


async def proxy_sse(
    provider_stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """
    Proxy SSE lines from provider to client unchanged.

    Args:
        provider_stream: Raw SSE lines from a provider.

    Yields:
        SSE data lines for the client.
    """
    async for line in provider_stream:
        yield line


def build_sse_chunk(
    content: str = "",
    model: str = "",
    chunk_id: str = "",
    finish_reason: str | None = None,
) -> str:
    """
    Build an SSE chunk in OpenAI format.

    Args:
        content: Text content for this chunk.
        model: Model name.
        chunk_id: Unique chunk ID.
        finish_reason: Finish reason if this is the last chunk.

    Returns:
        SSE-formatted string.
    """
    chunk = ChatCompletionChunk(
        id=chunk_id,
        model=model,
        choices=[
            StreamChoice(
                index=0,
                delta=DeltaMessage(content=content) if content else DeltaMessage(),
                finish_reason=finish_reason,
            )
        ],
    )
    return chunk.to_sse()
