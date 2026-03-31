"""
FreeRelay — Semantic Context Deduplication
=============================================
Detects and removes duplicate message content in conversation history.
Uses SHA256 hashing for exact duplicate detection.
"""

from __future__ import annotations

import hashlib
import logging

from freerelay.core.models.openai import Message

logger = logging.getLogger("freerelay.deduplicator")


def deduplicate_messages(messages: list[Message]) -> list[Message]:
    """
    Remove duplicate message content using SHA256 hashing.

    When the same content appears more than once, the first occurrence is kept
    and subsequent duplicates are replaced with a placeholder.

    Args:
        messages: List of chat messages.

    Returns:
        Deduplicated list of messages.
    """
    seen: dict[str, int] = {}
    result: list[Message] = []

    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else ""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if content_hash in seen:
            result.append(
                msg.model_copy(update={"content": "[Context repeated — see above]"})
            )
        else:
            seen[content_hash] = len(result)
            result.append(msg)

    return result
