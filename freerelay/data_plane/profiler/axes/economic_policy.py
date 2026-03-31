"""
FreeRelay Data Plane — Economic Policy Axis Classifier
=========================================================
Classifies economic policy: cheapest / balanced / best.

Rules:
  - Tenant policy lookup (default: balanced)
  - Keywords: cheap/budget/save → cheapest
  - Keywords: best/highest quality/accurate → best
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

_CHEAPEST_KEYWORDS = [
    "cheap",
    "budget",
    "save",
    "cost",
    "affordable",
    "economical",
    "free tier",
    "minimize cost",
    "low cost",
]

_BEST_KEYWORDS = [
    "best",
    "highest quality",
    "most accurate",
    "premium",
    "top tier",
    "maximum quality",
    "best model",
    "gpt-4",
]


def classify_economic_policy(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify the economic policy preference.

    Returns:
        (economic_policy, confidence) — policy in {cheapest, balanced, best}.
    """
    # Header-based tenant policy
    headers = headers or {}
    policy = headers.get("x-economic-policy", "").lower()
    if policy in ("cheapest", "balanced", "best"):
        return policy, 0.95

    text = request.get_content_text().lower()

    cheapest_hits = sum(1 for kw in _CHEAPEST_KEYWORDS if kw in text)
    best_hits = sum(1 for kw in _BEST_KEYWORDS if kw in text)

    if cheapest_hits >= 2:
        return "cheapest", min(0.90, 0.70 + cheapest_hits * 0.05)
    if best_hits >= 2:
        return "best", min(0.90, 0.70 + best_hits * 0.05)

    if cheapest_hits == 1 and best_hits == 0:
        return "cheapest", 0.65
    if best_hits == 1 and cheapest_hits == 0:
        return "best", 0.65

    # Default
    return "balanced", 0.60
