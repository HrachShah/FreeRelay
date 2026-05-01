"""
FreeRelay Data Plane — Output Contract Axis Classifier
=========================================================
Classifies output format: prose / json / schema / code_patch / tool_calls.

Rules:
  - response_format=json_object → json (confidence 0.95)
  - response_format with schema → schema (confidence 0.95)
  - tools + tool_choice → tool_calls (confidence 0.90)
  - Keywords: json/schema/format → json (confidence 0.80)
  - Keywords: code/patch → code_patch (confidence 0.75)
  - Else → prose (confidence 0.65)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest


def classify_output_contract(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify the expected output contract.

    Returns:
        (output_contract, confidence) — contract in {prose, json, schema, code_patch, tool_calls}.
    """
    # Tool calls output
    if request.tools and request.tool_choice is not None:
        choice_str = str(request.tool_choice).lower()
        if choice_str not in ('"none"', "none"):
            return "tool_calls", 0.90

    # Response format overrides
    if request.response_format is not None:
        fmt = request.response_format.type
        if fmt == "json_object":
            return "json", 0.95
        if fmt == "json_schema":
            return "schema", 0.95

    text = request.get_content_text().lower()

    # Schema keywords
    schema_keywords = [
        "json schema",
        "json_schema",
        "openapi",
        "swagger",
        "json schema output",
    ]
    if any(kw in text for kw in schema_keywords):
        return "schema", 0.85

    # JSON keywords
    json_keywords = [
        "json",
        "json format",
        "json output",
        "json object",
        "structured output",
    ]
    if any(kw in text for kw in json_keywords):
        return "json", 0.80

    # Code/patch keywords
    code_keywords = [
        "code",
        "patch",
        "diff",
        "function body",
        "implementation",
        "write a function",
    ]
    if any(kw in text for kw in code_keywords):
        return "code_patch", 0.75

    # System prompt hints
    for msg in request.messages:
        if msg.role == "system":
            content = (msg.content if isinstance(msg.content, str) else "").lower()
            if "json_object" in content or "structured output" in content:
                return "json", 0.80
            if "json" in content and ("schema" in content or "format" in content):
                return "schema", 0.80
            if "code" in content or "patch" in content:
                return "code_patch", 0.75

    return "prose", 0.65
