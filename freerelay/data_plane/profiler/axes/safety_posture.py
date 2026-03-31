"""
FreeRelay Data Plane — Safety Posture Axis Classifier
========================================================
Classifies safety posture: standard / locked_down / permissive.

Rules:
  - Tenant policy lookup (default: standard)
  - Keywords: legal/medical/finance/security → locked_down
  - Keyword: creative/fiction/story → permissive
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

_LOCKED_DOWN_KEYWORDS = [
    "legal",
    "medical",
    "finance",
    "security",
    "sensitive",
    "hipaa",
    "gdpr",
    "compliance",
    "classified",
    "confidential",
    "patient",
    "diagnosis",
    "prescription",
    "ssn",
    "social security",
    "credit card",
    "bank account",
    "password",
    "credential",
]

_PERMISSIVE_KEYWORDS = [
    "creative",
    "fiction",
    "story",
    "poem",
    "novel",
    "imagine",
    "fantasy",
    "roleplay",
    "character",
    "narrative",
]


def classify_safety_posture(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify safety posture.

    Returns:
        (safety_posture, confidence) — posture in {standard, locked_down, permissive}.
    """
    # Header-based tenant policy override
    headers = headers or {}
    policy = headers.get("x-safety-posture", "").lower()
    if policy in ("standard", "locked_down", "permissive"):
        return policy, 0.95

    text = request.get_content_text().lower()

    # Check for locked-down indicators
    locked_hits = sum(1 for kw in _LOCKED_DOWN_KEYWORDS if kw in text)
    if locked_hits >= 2:
        return "locked_down", min(0.95, 0.80 + locked_hits * 0.05)
    if locked_hits == 1:
        return "locked_down", 0.75

    # Check for permissive indicators
    permissive_hits = sum(1 for kw in _PERMISSIVE_KEYWORDS if kw in text)
    if permissive_hits >= 2:
        return "permissive", min(0.85, 0.65 + permissive_hits * 0.05)

    # System prompt safety directives
    for msg in request.messages:
        if msg.role == "system":
            content = msg.content if isinstance(msg.content, str) else ""
            content_lower = content.lower()
            if any(
                kw in content_lower for kw in ["strict", "no harmful", "safe", "refuse"]
            ):
                return "locked_down", 0.80

    return "standard", 0.70
