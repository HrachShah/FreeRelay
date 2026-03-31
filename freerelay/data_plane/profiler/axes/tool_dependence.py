"""
FreeRelay Data Plane — Tool Dependence Axis Classifier
=========================================================
Classifies tool dependence: none / optional / mandatory.

Rules:
  - tools defined in request → mandatory (confidence 0.95)
  - tool_choice explicitly set → mandatory (confidence 0.95)
  - Previous tool messages/calls → optional (confidence 0.80)
  - Else → none (confidence 0.90)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest


def classify_tool_dependence(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify tool dependence level.

    Returns:
        (tool_dependence, confidence) — tool_dependence in {none, optional, mandatory}.
    """
    # Tool definitions present → mandatory
    if request.tools:
        # Check if tool_choice forces tool use
        if request.tool_choice is not None:
            choice_str = str(request.tool_choice).lower()
            if choice_str in ("required", "auto", '"required"', '"auto"'):
                return "mandatory", 0.95
            if isinstance(request.tool_choice, dict):
                return "mandatory", 0.95
        return "mandatory", 0.90

    # Check message history for tool calls/results
    has_tool_messages = False
    for msg in request.messages:
        if msg.role == "tool" or msg.tool_calls:
            has_tool_messages = True
            break

    if has_tool_messages:
        return "optional", 0.80

    # Text hints about tool usage
    text = request.get_content_text().lower()
    tool_keywords = [
        "use a tool",
        "call function",
        "invoke",
        "use plugin",
        "function call",
    ]
    if any(kw in text for kw in tool_keywords):
        return "optional", 0.65

    return "none", 0.90
