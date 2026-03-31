"""
FreeRelay — Prompt Compression Pipeline (§15)
================================================
4-stage compression pipeline:
1. Structural cleanup
2. Conversation history summarization
3. Semantic deduplication
4. Quality gate
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from freerelay.core.models.openai import ChatCompletionRequest, Message

logger = logging.getLogger("freerelay.compressor")


@dataclass
class CompressionResult:
    """Result of prompt compression."""

    request: ChatCompletionRequest
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 1.0
    tokens_saved: int = 0
    stages_applied: list[str] = field(default_factory=list)


class PromptCompressor:
    """
    4-stage prompt compression pipeline.

    Each stage is independently configurable and can be disabled.
    """

    def __init__(
        self,
        enabled: bool = True,
        summarize_threshold: int = 8000,
        min_ratio: float = 0.5,
    ) -> None:
        self.enabled = enabled
        self.summarize_threshold = summarize_threshold
        self.min_ratio = min_ratio

    def compress(self, request: ChatCompletionRequest) -> CompressionResult:
        """
        Run the full compression pipeline on a request.

        Args:
            request: Original chat completion request.

        Returns:
            CompressionResult with the (potentially modified) request.
        """
        if not self.enabled:
            return CompressionResult(
                request=request,
                original_tokens=request.estimate_tokens(),
            )

        original_tokens = request.estimate_tokens()
        messages = list(request.messages)
        stages_applied: list[str] = []

        # Stage 1: Structural cleanup
        messages, applied = self._stage1_cleanup(messages)
        if applied:
            stages_applied.append("structural_cleanup")

        # Stage 2: Conversation history summarization
        total_tokens = self._estimate_messages_tokens(messages)
        if total_tokens > self.summarize_threshold:
            messages, applied = self._stage2_summarize(messages)
            if applied:
                stages_applied.append("summarization")

        # Stage 3: Semantic deduplication
        messages, applied = self._stage3_deduplicate(messages)
        if applied:
            stages_applied.append("deduplication")

        # Stage 4: Quality gate
        compressed_tokens = self._estimate_messages_tokens(messages)
        compression_ratio = compressed_tokens / max(1, original_tokens)

        if compression_ratio < self.min_ratio:
            # Quality gate: too much lost, revert
            logger.warning(
                "Compression ratio %.2f below threshold %.2f — reverting",
                compression_ratio,
                self.min_ratio,
            )
            messages = list(request.messages)
            compressed_tokens = original_tokens
            compression_ratio = 1.0
            stages_applied.append("quality_gate_revert")

        # Build compressed request
        compressed_request = request.model_copy(update={"messages": messages})

        return CompressionResult(
            request=compressed_request,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
            tokens_saved=max(0, original_tokens - compressed_tokens),
            stages_applied=stages_applied,
        )

    def _stage1_cleanup(self, messages: list[Message]) -> tuple[list[Message], bool]:
        """Stage 1: Structural cleanup."""
        changed = False
        cleaned: list[Message] = []

        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                # Strip leading/trailing whitespace
                stripped = content.strip()
                # Collapse consecutive blank lines
                collapsed = re.sub(r"\n{3,}", "\n\n", stripped)
                if stripped != content or collapsed != stripped:
                    changed = True

                if not collapsed:
                    continue  # Remove empty messages
                cleaned.append(msg.model_copy(update={"content": collapsed}))
            else:
                if content is not None:
                    cleaned.append(msg)

        return cleaned, changed

    def _stage2_summarize(self, messages: list[Message]) -> tuple[list[Message], bool]:
        """
        Stage 2: Conversation history summarization.
        Keeps the last 4 messages intact and marks older ones for summarization.
        In production, this would call a cheap provider to summarize.
        Here we just truncate and note the summarization.
        """
        if len(messages) <= 5:
            return messages, False

        recent = messages[-4:]
        older = messages[:-4]

        # In production: send older to cheapest provider for summarization
        # Here: extract a brief summary placeholder
        summary_parts: list[str] = []
        for m in older:
            if isinstance(m.content, str):
                preview = m.content[:100]
                summary_parts.append(f"[{m.role}]: {preview}...")

        summary_text = (
            f"[Previous conversation summary: "
            f"{len(older)} messages summarized. "
            f"Topics: {'; '.join(summary_parts[:3])}]"
        )

        summary_msg = Message(role="system", content=summary_text)
        return [summary_msg] + recent, True

    def _stage3_deduplicate(
        self, messages: list[Message]
    ) -> tuple[list[Message], bool]:
        """Stage 3: Semantic deduplication via content hashing."""
        seen_hashes: dict[str, int] = {}
        deduped: list[Message] = []
        changed = False

        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else ""
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            if content_hash in seen_hashes:
                deduped.append(
                    msg.model_copy(update={"content": "[Context repeated — see above]"})
                )
                changed = True
            else:
                seen_hashes[content_hash] = len(deduped)
                deduped.append(msg)

        return deduped, changed

    def _estimate_messages_tokens(self, messages: list[Message]) -> int:
        """Rough token estimate for a list of messages."""
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content) // 4
            elif isinstance(msg.content, list):
                for part in msg.content:
                    if part.text:
                        total += len(part.text) // 4
        return max(1, total)
