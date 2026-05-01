"""
FreeRelay — Intent Classifier (§14 + feature 4)
==================================================
Classifies request intent using heuristics for <5ms latency.
Labels: coding, math, chat, creative, multilingual, general.
"""

from __future__ import annotations

import re

from freerelay.core.models.openai import ChatCompletionRequest

# Keyword sets for classification
_CODING_KEYWORDS = {
    "code",
    "function",
    "class",
    "def",
    "import",
    "variable",
    "bug",
    "error",
    "debug",
    "compile",
    "syntax",
    "algorithm",
    "api",
    "json",
    "html",
    "css",
    "javascript",
    "python",
    "java",
    "refactor",
    "implement",
    "script",
    "database",
    "sql",
    "query",
    "regex",
    "test",
    "unittest",
    "git",
}

_MATH_KEYWORDS = {
    "calculate",
    "equation",
    "formula",
    "integral",
    "derivative",
    "proof",
    "theorem",
    "solve",
    "math",
    "algebra",
    "calculus",
    "statistics",
    "probability",
    "matrix",
    "eigenvalue",
    "optimization",
    "geometry",
}

_CREATIVE_KEYWORDS = {
    "write",
    "story",
    "poem",
    "creative",
    "imagine",
    "fiction",
    "character",
    "dialogue",
    "narrative",
    "novel",
    "song",
    "lyrics",
    "screenplay",
    "brainstorm",
    "metaphor",
    "haiku",
}

# Non-Latin script ranges for multilingual detection
_NON_LATIN_RE = re.compile(
    r"[\u0400-\u04FF"  # Cyrillic
    r"\u0600-\u06FF"  # Arabic
    r"\u4E00-\u9FFF"  # CJK
    r"\u3040-\u309F"  # Hiragana
    r"\u30A0-\u30FF"  # Katakana
    r"\uAC00-\uD7AF"  # Korean
    r"\u0900-\u097F"  # Devanagari
    r"]"
)


def classify_intent(request: ChatCompletionRequest) -> str:
    """
    Classify request intent via keyword heuristics.
    Runs in <5ms — no model inference.

    Returns one of: coding, math, chat, creative, multilingual, general.
    """
    text = request.get_content_text().lower()
    words = set(text.split())

    # Check for tool use → likely coding
    if request.tools:
        return "coding"

    # Check for non-Latin characters → multilingual
    if _NON_LATIN_RE.search(text):
        return "multilingual"

    # Score each intent
    coding_score = len(words & _CODING_KEYWORDS)
    math_score = len(words & _MATH_KEYWORDS)
    creative_score = len(words & _CREATIVE_KEYWORDS)

    scores = {
        "coding": coding_score,
        "math": math_score,
        "creative": creative_score,
    }

    best = max(scores, key=scores.get, default=None)  # type: ignore[arg-type]
    if best is None or scores[best] < 2:
        return "general"

    # Short messages with questions → simple chat
    if len(text) < 100:
        return "chat"

    return "general"
