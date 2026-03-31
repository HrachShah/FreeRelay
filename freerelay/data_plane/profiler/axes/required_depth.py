"""
FreeRelay Data Plane — Required Depth Axis Classifier
========================================================
Heuristic classifier for analysis depth: shallow / medium / deep.

Rules:
  - token_count > 6000 → deep (confidence 0.85)
  - Keywords indicating depth → deep/shallow (confidence 0.7-0.9)
  - token_count > 2000 → medium (confidence 0.7)
  - Else → shallow (confidence 0.6)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

_DEEP_KEYWORDS = [
    "analysis",
    "deep",
    "thorough",
    "thoughtful",
    "complex",
    "detailed",
    "comprehensive",
    "in-depth",
    "elaborate",
    "nuanced",
    "rigorous",
    "investigate",
    "examine",
    "critically",
]

_SHALLOW_KEYWORDS = [
    "quick",
    "brief",
    "simple",
    "short",
    "one-liner",
    "concise",
    "tldr",
    "summary only",
    "just tell me",
    "yes or no",
]


def classify_required_depth(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify the required depth of analysis.

    Returns:
        (depth_level, confidence) — depth_level in {shallow, medium, deep}.
    """
    text = request.get_content_text().lower()
    tokens = request.estimate_tokens()

    # Keyword-based overrides
    deep_hits = sum(1 for kw in _DEEP_KEYWORDS if kw in text)
    shallow_hits = sum(1 for kw in _SHALLOW_KEYWORDS if kw in text)

    if deep_hits >= 2:
        return "deep", min(0.95, 0.7 + deep_hits * 0.08)

    if shallow_hits >= 1 and deep_hits == 0:
        return "shallow", min(0.90, 0.6 + shallow_hits * 0.1)

    # Token-count heuristics
    if tokens > 6000:
        return "deep", 0.85

    if tokens > 2000:
        return "medium", 0.70

    if tokens > 800:
        return "medium", 0.60

    return "shallow", 0.60
