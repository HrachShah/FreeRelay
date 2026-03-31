"""
FreeRelay — Context Optimizer (§8)
======================================
Combines prompt compression with structured lanes, salience, and packing heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from freerelay.core.intelligence.compressor import CompressionResult, PromptCompressor
from freerelay.core.models.openai import ChatCompletionRequest, Message


@dataclass
class ContextBundle:
    """Result of the context optimizer."""

    optimized_request: ChatCompletionRequest
    compression: CompressionResult
    lanes: dict[str, list[Message]]
    salience_order: list[int]
    total_tokens: int
    packing_summary: dict[str, int] = field(default_factory=dict)


class ContextOptimizer:
    """Wraps prompt compression and adds structural context insights."""

    def __init__(self, compressor: PromptCompressor) -> None:
        self.compressor = compressor

    def optimize(self, request: ChatCompletionRequest) -> ContextBundle:
        compression = self.compressor.compress(request)
        optimized = compression.request
        lanes = self._build_lanes(optimized.messages)
        salience = self._rank_salience(optimized.messages)
        packing = {lane: len(msgs) for lane, msgs in lanes.items()}

        return ContextBundle(
            optimized_request=optimized,
            compression=compression,
            lanes=lanes,
            salience_order=salience,
            total_tokens=optimized.estimate_tokens(),
            packing_summary=packing,
        )

    def _build_lanes(self, messages: Sequence[Message]) -> dict[str, list[Message]]:
        lanes: dict[str, list[Message]] = {
            "instructions": [],
            "memory": [],
            "facts": [],
            "dialogue": [],
            "tool_outputs": [],
            "scratch": [],
        }

        for msg in messages:
            if msg.role == "system":
                lanes["instructions"].append(msg)
            elif msg.role == "tool" or msg.tool_calls:
                lanes["tool_outputs"].append(msg)
            elif msg.role == "assistant":
                lanes["dialogue"].append(msg)
            elif msg.role == "function":
                lanes["facts"].append(msg)
            elif msg.role == "user":
                content = msg.content if isinstance(msg.content, str) else ""
                normalized = content.lower()
                if "remember" in normalized or "note" in normalized:
                    lanes["memory"].append(msg)
                else:
                    lanes["dialogue"].append(msg)
            else:
                lanes["scratch"].append(msg)

        return lanes

    def _rank_salience(self, messages: Sequence[Message]) -> list[int]:
        scores: list[tuple[int, int]] = []
        for idx, msg in enumerate(messages):
            content = msg.content if isinstance(msg.content, str) else ""
            token_estimate = max(1, len(content) // 4)
            scores.append((token_estimate, idx))
        scores.sort(reverse=True)
        return [idx for _, idx in scores]
