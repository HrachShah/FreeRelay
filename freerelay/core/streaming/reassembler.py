"""
FreeRelay — Chunk Reassembler (§12)
======================================
Reassembles streaming chunks into a complete response
for caching and logging after the stream completes.
"""

from __future__ import annotations

import time
import uuid

from freerelay.core.models.openai import (
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    Message,
    Usage,
)


def reassemble_chunks(chunks: list[ChatCompletionChunk]) -> ChatCompletionResponse:
    """
    Reassemble streaming chunks into a complete ChatCompletionResponse.

    Used after streaming completes to store the full response in the cache
    and compute final usage statistics.

    Args:
        chunks: List of streaming chunks received.

    Returns:
        Complete ChatCompletionResponse.
    """
    if not chunks:
        return ChatCompletionResponse.from_text("")

    content_parts: list[str] = []
    model = ""
    chunk_id = ""

    for chunk in chunks:
        if chunk.model:
            model = chunk.model
        if chunk.id:
            chunk_id = chunk.id
        for choice in chunk.choices:
            if choice.delta and choice.delta.content:
                content_parts.append(choice.delta.content)

    full_content = "".join(content_parts)

    # Get usage from last chunk if available
    usage = Usage()
    if chunks[-1].usage:
        usage = chunks[-1].usage

    return ChatCompletionResponse(
        id=chunk_id or f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=full_content),
                finish_reason="stop",
            )
        ],
        usage=usage,
    )


class ChunkAccumulator:
    """Accumulates streaming chunks for later reassembly."""

    def __init__(self) -> None:
        self.chunks: list[ChatCompletionChunk] = []

    def add(self, chunk: ChatCompletionChunk) -> None:
        """Add a chunk to the accumulator."""
        self.chunks.append(chunk)

    def to_response(self) -> ChatCompletionResponse:
        """Reassemble all accumulated chunks into a response."""
        return reassemble_chunks(self.chunks)

    def clear(self) -> None:
        """Clear accumulated chunks."""
        self.chunks.clear()
