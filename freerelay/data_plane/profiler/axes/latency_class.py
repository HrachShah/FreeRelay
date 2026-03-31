"""
FreeRelay Data Plane — Latency Class Axis Classifier
========================================================
Classifies latency expectations: interactive / async / batch.

Rules:
  - stream=true → interactive (confidence 0.95)
  - max_tokens > 4000 → batch (confidence 0.80)
  - token_count < 1000, no tools → interactive (confidence 0.75)
  - Else → async (confidence 0.65)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

_INTERACTIVE_HEADERS = {"x-latency-class": "interactive"}


def classify_latency_class(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify the latency expectation class.

    Returns:
        (latency_class, confidence) — latency_class in {interactive, async, batch}.
    """
    headers = headers or {}

    # Header-based override
    header_class = headers.get("x-latency-class", "").lower()
    if header_class in ("interactive", "async", "batch"):
        return header_class, 0.90

    # Streaming implies interactive
    if request.is_streaming():
        return "interactive", 0.95

    # Large max_tokens suggests batch
    max_tokens = request.max_tokens or 0
    if max_tokens > 4000:
        return "batch", 0.80

    # Short requests without tools are typically interactive
    tokens = request.estimate_tokens()
    if tokens < 1000 and not request.tools:
        return "interactive", 0.75

    # Medium-length requests
    if tokens < 3000:
        return "async", 0.65

    return "batch", 0.70
