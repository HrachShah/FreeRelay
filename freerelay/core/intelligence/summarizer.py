"""
FreeRelay — Conversation History Summarizer
===============================================
Summarizes old conversation messages to reduce token usage.
Used by the compression pipeline (Stage 2).
"""

from __future__ import annotations

import logging

from freerelay.core.models.openai import Message

logger = logging.getLogger("freerelay.summarizer")


def summarize_messages(
    messages: list[Message],
    keep_last_n: int = 4,
    max_summary_tokens: int = 200,
) -> list[Message]:
    """
    Summarize older messages, keeping recent context intact.

    In production, this calls the cheapest available provider.
    Here we use a extractive approach.

    Args:
        messages: Full conversation messages.
        keep_last_n: Number of recent messages to keep intact.
        max_summary_tokens: Target max tokens for the summary.

    Returns:
        List of messages with older ones summarized.
    """
    if keep_last_n < 0:
        raise ValueError("keep_last_n must be non-negative")
    if max_summary_tokens < 1:
        raise ValueError("max_summary_tokens must be positive")
    if len(messages) <= keep_last_n + 1:
        return messages

    recent = messages[-keep_last_n:] if keep_last_n else []
    older = messages[:-keep_last_n] if keep_last_n else messages

    # Build extractive summary
    key_points: list[str] = []
    for msg in older:
        content = msg.content if isinstance(msg.content, str) else ""
        if content:
            # Take first sentence as key point
            first_sentence = content.split(".")[0].strip()
            if first_sentence:
                key_points.append(f"{msg.role}: {first_sentence}")

    summary_text = (
        f"Previous conversation covered: {'; '.join(key_points[:5])}"
        if key_points
        else "Previous conversation context summarized."
    )

    summary_msg = Message(role="system", content=f"[Summary: {summary_text}]")
    return [summary_msg] + recent
