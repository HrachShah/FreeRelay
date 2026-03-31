"""
FreeRelay Data Plane — Context Topology Axis Classifier
===========================================================
Classifies context shape: short / long / multimodal / structured / fragmented.

Rules:
  - prompt_tokens > 32000 → long (confidence 0.90)
  - Images present → multimodal (confidence 0.95)
  - Structured content (tables, JSON) → structured (confidence 0.80)
  - Fragmented markers → fragmented (confidence 0.75)
  - Else → short (confidence 0.65)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest


def classify_context_topology(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify the context topology.

    Returns:
        (topology, confidence) — topology in {short, long, multimodal, structured, fragmented}.
    """
    text = request.get_content_text()
    text_lower = text.lower()
    tokens = request.estimate_tokens()

    # Check for multimodal content (images)
    has_images = False
    for msg in request.messages:
        if isinstance(msg.content, list):
            for part in msg.content:
                if part.type == "image_url":
                    has_images = True
                    break
        if has_images:
            break

    if has_images:
        return "multimodal", 0.95

    # Long context
    if tokens > 32000:
        return "long", 0.90

    if tokens > 16000:
        return "long", 0.80

    # Structured content indicators
    structured_indicators = [
        "table",
        "|---|",
        "```json",
        "```yaml",
        "```csv",
        "structured",
    ]
    structured_hits = sum(1 for ind in structured_indicators if ind in text_lower)
    if structured_hits >= 2:
        return "structured", 0.80

    # Fragmented indicators
    fragmented_indicators = ["...", "---", "part 1", "part 2", "section", "continued"]
    fragmented_hits = sum(1 for ind in fragmented_indicators if ind in text_lower)
    if fragmented_hits >= 2:
        return "fragmented", 0.75

    # Multiple user messages suggest fragmented conversation
    user_msgs = sum(1 for m in request.messages if m.role == "user")
    if user_msgs > 5:
        return "fragmented", 0.70

    # Long text but not extremely long
    if tokens > 4000:
        return "long", 0.70

    return "short", 0.65
