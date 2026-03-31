"""
FreeRelay Data Plane — Task Family Axis Classifier
=====================================================
8-class keyword heuristic with optional sklearn fallback.
Target: <1ms latency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.core.models.openai import ChatCompletionRequest

_TASK_KEYWORDS: dict[str, list[str]] = {
    "tool_use": [
        "function_call",
        "tool_call",
        "invoke",
        "plugin",
        "tool_use",
        "call_function",
        "use_tool",
        "tool_choice",
        "functions",
    ],
    "coding": [
        "code",
        "function",
        "debug",
        "compile",
        "syntax",
        "json",
        "api",
        "script",
        "database",
        "python",
        "javascript",
        "typescript",
        "rust",
        "golang",
        "java",
        "implement",
        "refactor",
        "algorithm",
        "bug",
        "class",
        "method",
        "variable",
        "import",
        "module",
        "regex",
    ],
    "extraction": [
        "extract",
        "parse",
        "summarize",
        "retrieve",
        "extract data",
        "parse json",
        "get fields",
        "pull out",
        "find in text",
    ],
    "planning": [
        "plan",
        "strategy",
        "roadmap",
        "sequence",
        "steps",
        "agenda",
        "break down",
        "decompose",
        "organize",
        "schedule",
        "prioritize",
    ],
    "rag": [
        "source",
        "reference",
        "document",
        "retrieval",
        "cite",
        "according to",
        "based on the context",
        "given the following",
        "passage",
        "article",
        "paper",
    ],
    "eval": [
        "evaluate",
        "score",
        "judge",
        "testcase",
        "benchmark",
        "grade",
        "assess",
        "rate",
        "compare",
        "rank",
        "rubric",
    ],
    "agent_loop": [
        "plan_and_execute",
        "chain of thought",
        "step by step",
        "agent",
        "loop",
        "iteratively",
        "re_act",
        "multi-step",
        "workflow",
    ],
    "chat": [
        "hello",
        "hi",
        "hey",
        "how are you",
        "what is",
        "explain",
        "tell me",
        "help me",
        "can you",
        "please",
        "thank",
    ],
}


def classify_task_family(
    request: ChatCompletionRequest,
    headers: dict[str, str] | None = None,
) -> tuple[str, float]:
    """
    Classify the task family using keyword heuristics.

    Returns:
        (task_family, confidence) — confidence in [0.0, 1.0].
    """
    if request.tools:
        return "tool_use", 0.95

    system_text = ""
    user_text = ""
    for msg in request.messages:
        content = msg.content if isinstance(msg.content, str) else ""
        if msg.role == "system":
            system_text += content.lower() + " "
        else:
            user_text += content.lower() + " "

    best_family = "chat"
    best_score = 0.0

    for family, keywords in _TASK_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if kw in system_text:
                score += 2.0
            if kw in user_text:
                score += 1.0
        if score > best_score:
            best_score = score
            best_family = family

    if best_score < 1.0:
        return "chat", 0.5

    confidence = min(0.95, 0.5 + best_score * 0.05)
    return best_family, confidence
