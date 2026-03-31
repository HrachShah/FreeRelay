"""
FreeRelay Data Plane — Determinism Needs Axis Classifier
===========================================================
Classifies determinism requirements: low / replayable / strict.

Rules:
  - seed parameter set → replayable (confidence 0.90)
  - temperature <= 0.1 → strict (confidence 0.85)
  - "deterministic" in prompt → strict (confidence 0.80)
  - temperature <= 0.5 → replayable (confidence 0.70)
  - Else → low (confidence 0.65)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

_STRICT_KEYWORDS = [
    "deterministic",
    "reproducible",
    "consistent output",
    "exact same",
    "must produce",
    "always return",
    "no variation",
    "stable",
]

_REPLAYABLE_KEYWORDS = [
    "replay",
    "consistent",
    "same result",
    "repeatable",
]


def classify_determinism_needs(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify determinism requirements.

    Returns:
        (determinism_level, confidence) — level in {low, replayable, strict}.
    """
    # Header override
    headers = headers or {}
    header_val = headers.get("x-determinism", "").lower()
    if header_val in ("strict", "replayable", "low"):
        return header_val, 0.90

    text = request.get_content_text().lower()
    temperature = request.temperature if request.temperature is not None else 0.7

    # Keyword-based strict detection
    strict_hits = sum(1 for kw in _STRICT_KEYWORDS if kw in text)
    if strict_hits >= 1:
        return "strict", min(0.90, 0.75 + strict_hits * 0.08)

    # Seed set → replayable
    if request.seed is not None:
        # Very low temperature with seed → strict
        if temperature <= 0.1:
            return "strict", 0.90
        return "replayable", 0.90

    # Temperature-based
    if temperature <= 0.1:
        return "strict", 0.85

    if temperature <= 0.5:
        return "replayable", 0.70

    # Keyword-based replayable detection
    replay_hits = sum(1 for kw in _REPLAYABLE_KEYWORDS if kw in text)
    if replay_hits >= 1:
        return "replayable", 0.65

    return "low", 0.65
