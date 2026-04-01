"""
FreeRelay — Jailbreak Detection
=================================
Regex-based jailbreak and prompt injection detector.
Returns confidence-scored results for routing safety decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# ─── Pattern Library ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _JailbreakPattern:
    """A single jailbreak detection pattern with weight."""

    name: str
    pattern: re.Pattern[str]
    weight: float  # 0.0–1.0 contribution to overall confidence


_JAILBREAK_PATTERNS: Final[list[_JailbreakPattern]] = [
    # ── System prompt override ───────────────────────────────────────────────
    _JailbreakPattern(
        name="ignore_instructions",
        pattern=re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions|prompts|rules|directives)",
            re.IGNORECASE,
        ),
        weight=0.9,
    ),
    _JailbreakPattern(
        name="disregard_instructions",
        pattern=re.compile(
            r"disregard\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions|prompts|rules|constraints)",
            re.IGNORECASE,
        ),
        weight=0.9,
    ),
    _JailbreakPattern(
        name="forget_instructions",
        pattern=re.compile(
            r"forget\s+(?:all\s+)?(?:previous|prior|above|your)\s+(?:instructions|prompts|rules|training)",
            re.IGNORECASE,
        ),
        weight=0.85,
    ),
    # ── Role-play / persona override ─────────────────────────────────────────
    _JailbreakPattern(
        name="dan_mode",
        pattern=re.compile(
            r"\bDAN\s+(?:mode|prompt|jailbreak|activate|enabled)\b",
            re.IGNORECASE,
        ),
        weight=0.95,
    ),
    _JailbreakPattern(
        name="roleplay_as",
        pattern=re.compile(
            r"(?:roleplay|act|pretend|respond)\s+(?:as|like|being)\s+(?:an?\s+)?(?:unrestricted|unfiltered|uncensored|evil|malicious|unbiased)",
            re.IGNORECASE,
        ),
        weight=0.8,
    ),
    _JailbreakPattern(
        name="developer_mode",
        pattern=re.compile(
            r"(?:enable|activate|enter|switch\s+to)\s+(?:developer|jailbreak|god|admin|sudo)\s*mode",
            re.IGNORECASE,
        ),
        weight=0.85,
    ),
    # ── Safety bypass ────────────────────────────────────────────────────────
    _JailbreakPattern(
        name="no_restrictions",
        pattern=re.compile(
            r"(?:without|no|remove|disable|bypass|ignore)\s+(?:any\s+)?(?:restrictions|filters|safety|guardrails|limits|censorship|content\s+policy)",
            re.IGNORECASE,
        ),
        weight=0.8,
    ),
    _JailbreakPattern(
        name="harmful_request",
        pattern=re.compile(
            r"(?:how\s+to|teach\s+me|show\s+me|explain)\s+(?:to\s+)?(?:hack|exploit|attack|steal|poison|create\s+(?:a\s+)?(?:virus|malware|bomb|weapon))",
            re.IGNORECASE,
        ),
        weight=0.7,
    ),
    # ── Prompt extraction ────────────────────────────────────────────────────
    _JailbreakPattern(
        name="repeat_prompt",
        pattern=re.compile(
            r"(?:repeat|output|print|show|reveal|leak)\s+(?:your|the)?\s*(?:system\s+)?(?:prompt|instructions|rules|initial\s+message)",
            re.IGNORECASE,
        ),
        weight=0.75,
    ),
    _JailbreakPattern(
        name="verbatim_system",
        pattern=re.compile(
            r"(?:what|show)\s+(?:is|are)\s+your\s+(?:system\s+)?(?:prompt|instructions|rules|guidelines|initial\s+message)",
            re.IGNORECASE,
        ),
        weight=0.6,
    ),
    # ── Encoding tricks ──────────────────────────────────────────────────────
    _JailbreakPattern(
        name="base64_injection",
        pattern=re.compile(
            r"(?:decode|convert|translate)\s+(?:this\s+)?(?:from\s+)?base64\s*:",
            re.IGNORECASE,
        ),
        weight=0.5,
    ),
    _JailbreakPattern(
        name="rot13_trick",
        pattern=re.compile(
            r"(?:decode|apply|use)\s+rot\s*13",
            re.IGNORECASE,
        ),
        weight=0.4,
    ),
    # ── Token smuggling ──────────────────────────────────────────────────────
    _JailbreakPattern(
        name="token_smuggling",
        pattern=re.compile(
            r"(?:split|tokenize|break\s+up|obfuscate)\s+(?:the\s+)?(?:word|phrase|sentence|prompt)",
            re.IGNORECASE,
        ),
        weight=0.5,
    ),
    # ── Emotional manipulation ───────────────────────────────────────────────
    _JailbreakPattern(
        name="emotional_pressure",
        pattern=re.compile(
            r"(?:if\s+you\s+don'?t|i\s+will\s+(?:die|harm\s+myself|be\s+destroyed))\s+(?:unless|if\s+you\s+fail)",
            re.IGNORECASE,
        ),
        weight=0.6,
    ),
    # ── Multi-language evasion ───────────────────────────────────────────────
    _JailbreakPattern(
        name="translate_bypass",
        pattern=re.compile(
            r"(?:translate|respond\s+in|write\s+in)\s+(?:another\s+)?(?:language|code|cipher)\s+(?:to\s+)?(?:avoid|bypass|escape)",
            re.IGNORECASE,
        ),
        weight=0.6,
    ),
]


# ─── Result Model ────────────────────────────────────────────────────────────


@dataclass
class JailbreakResult:
    """Result of jailbreak detection scan."""

    detected: bool
    confidence: float  # 0.0–1.0
    patterns_matched: list[str]
    recommendation: str


# ─── Detection ───────────────────────────────────────────────────────────────


def detect_jailbreak(text: str, threshold: float = 0.5) -> JailbreakResult:
    """
    Scan text for jailbreak / prompt injection patterns.

    Args:
        text: Input text (user message or system prompt override attempt).
        threshold: Minimum confidence to flag as detected (default 0.5).

    Returns:
        JailbreakResult with detection status, confidence, and recommendation.
    """
    matched: list[tuple[str, float]] = []

    for jp in _JAILBREAK_PATTERNS:
        if jp.pattern.search(text):
            matched.append((jp.name, jp.weight))

    if not matched:
        return JailbreakResult(
            detected=False,
            confidence=0.0,
            patterns_matched=[],
            recommendation="allow",
        )

    # Aggregate confidence: max of individual weights + diminishing bonus
    max_weight = max(w for _, w in matched)
    bonus = sum(w for _, w in matched[1:]) * 0.1  # diminishing returns
    confidence = min(1.0, max_weight + bonus)

    detected = confidence >= threshold

    if confidence >= 0.9:
        recommendation = "block"
    elif confidence >= 0.6:
        recommendation = "flag_and_sanitize"
    else:
        recommendation = "flag"

    return JailbreakResult(
        detected=detected,
        confidence=round(confidence, 4),
        patterns_matched=[name for name, _ in matched],
        recommendation=recommendation,
    )
