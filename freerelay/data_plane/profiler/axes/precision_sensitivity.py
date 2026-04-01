"""
FreeRelay Data Plane — Precision Sensitivity Axis Classifier
===============================================================
Rule table over (task_family, output_contract) combinations.
High-precision tasks: coding, eval, extraction with structured output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

# Rule table: (task_family, output_contract) → (precision, confidence)
_PRECISION_RULES: dict[tuple[str, str], tuple[str, float]] = {
    ("coding", "json"): ("high", 0.90),
    ("coding", "schema"): ("high", 0.95),
    ("coding", "code_patch"): ("high", 0.95),
    ("coding", "prose"): ("medium", 0.70),
    ("eval", "json"): ("high", 0.90),
    ("eval", "schema"): ("high", 0.95),
    ("eval", "prose"): ("medium", 0.75),
    ("extraction", "json"): ("high", 0.90),
    ("extraction", "schema"): ("high", 0.95),
    ("extraction", "prose"): ("medium", 0.70),
    ("tool_use", "json"): ("high", 0.85),
    ("tool_use", "schema"): ("high", 0.90),
    ("tool_use", "prose"): ("medium", 0.65),
    ("planning", "json"): ("medium", 0.75),
    ("planning", "prose"): ("medium", 0.70),
    ("rag", "json"): ("medium", 0.75),
    ("rag", "prose"): ("medium", 0.65),
    ("chat", "json"): ("medium", 0.70),
    ("chat", "prose"): ("low", 0.60),
    ("agent_loop", "json"): ("medium", 0.75),
    ("agent_loop", "prose"): ("low", 0.55),
}

_PRECISION_KEYWORDS = [
    "exact",
    "precise",
    "strict",
    "validate",
    "certify",
    "legal",
    "medical",
    "correct",
    "accurate",
    "no mistakes",
    "flawless",
    "error-free",
    "must be",
    "required",
    "mandatory",
]


def classify_precision_sensitivity(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify precision sensitivity using rule table + keyword overlay.

    Returns:
        (precision_level, confidence) — precision_level in {low, medium, high}.
    """
    from freerelay.data_plane.profiler.axes.output_contract import (
        classify_output_contract,
    )
    from freerelay.data_plane.profiler.axes.task_family import classify_task_family

    task_family, _ = classify_task_family(request, headers)
    output_contract, _ = classify_output_contract(request, headers)

    # Look up rule table
    key = (task_family, output_contract)
    if key in _PRECISION_RULES:
        precision, confidence = _PRECISION_RULES[key]
    else:
        # Fallback defaults
        if task_family in ("coding", "eval", "extraction"):
            precision, confidence = "medium", 0.65
        else:
            precision, confidence = "low", 0.55

    # Keyword overlay — boost precision if precision keywords present
    text = request.get_content_text().lower()
    keyword_hits = sum(1 for kw in _PRECISION_KEYWORDS if kw in text)

    if keyword_hits >= 2:
        precision = "high"
        confidence = min(0.95, confidence + 0.15)
    elif keyword_hits == 1 and precision == "low":
        precision = "medium"
        confidence = min(0.85, confidence + 0.10)

    return precision, confidence
