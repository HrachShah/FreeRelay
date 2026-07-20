"""
FreeRelay — PII Detection & Masking
=====================================
Regex-based PII detector for email, phone, SSN, credit card, and IP addresses.
Provides masking/unmasking with typed placeholders for safe prompt forwarding.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final

# ─── PII Detection Patterns ──────────────────────────────────────────────────

_PII_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "PHONE": re.compile(
        r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}"
        r"|\+\d{1,3}[\s.-]?\d{4,14}"
    ),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CC": re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
    "IP": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


# ─── Data Classes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PIIDetection:
    """A single detected PII occurrence."""

    pii_type: str
    start: int
    end: int
    value_hash: str


@dataclass
class MaskResult:
    """Result of masking PII from text."""

    masked_text: str
    replacement_map: dict[str, str]
    detections: list[PIIDetection]


# ─── Detection ───────────────────────────────────────────────────────────────


def _hash_value(value: str) -> str:
    """SHA-256 hex digest of the PII value (never store raw PII)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def detect_pii(text: str) -> list[PIIDetection]:
    """
    Detect PII in the given text.

    Args:
        text: Input text to scan.

    Returns:
        List of PIIDetection objects with type, position, and value hash.
    """
    detections: list[PIIDetection] = []

    for pii_type, pattern in _PII_PATTERNS.items():
        for match in pattern.finditer(text):
            # Skip false-positive IPs (e.g. version numbers like 1.2.3.4)
            if pii_type == "IP":
                octets = match.group().split(".")
                if any(int(o) > 255 for o in octets):
                    continue

            detections.append(
                PIIDetection(
                    pii_type=pii_type,
                    start=match.start(),
                    end=match.end(),
                    value_hash=_hash_value(match.group()),
                )
            )

    # Sort by position and prefer the longest match at the same offset so
    # overlapping detectors do not produce invalid replacement spans.
    detections.sort(key=lambda d: (d.start, -(d.end - d.start)))
    non_overlapping: list[PIIDetection] = []
    for detection in detections:
        if non_overlapping and detection.start < non_overlapping[-1].end:
            continue
        non_overlapping.append(detection)
    detections = non_overlapping
    return detections


# ─── Masking ─────────────────────────────────────────────────────────────────


def mask_pii(text: str, detections: list[PIIDetection] | None = None) -> MaskResult:
    """
    Replace PII with typed placeholders.

    Args:
        text: Original text.
        detections: Pre-computed detections (if None, runs detect_pii first).

    Returns:
        MaskResult with masked text and a map for later unmasking.
    """
    if detections is None:
        detections = detect_pii(text)

    ordered_detections: list[PIIDetection] = []
    occupied_until = -1
    for detection in sorted(
        detections,
        key=lambda item: (item.start, -(item.end - item.start), item.pii_type),
    ):
        if detection.start < occupied_until:
            continue
        ordered_detections.append(detection)
        occupied_until = detection.end

    counters: dict[str, int] = {}
    replacement_map: dict[str, str] = {}
    result = list(text)

    # Process in reverse order so indices stay valid
    for det in reversed(ordered_detections):
        counters[det.pii_type] = counters.get(det.pii_type, 0) + 1
        idx = counters[det.pii_type]
        placeholder = f"[{det.pii_type}_{idx}]"

        original_value = text[det.start : det.end]
        replacement_map[placeholder] = original_value

        result[det.start : det.end] = list(placeholder)

    return MaskResult(
        masked_text="".join(result),
        replacement_map=replacement_map,
        detections=ordered_detections,
    )


# ─── Unmasking ───────────────────────────────────────────────────────────────


def unmask_pii(masked_text: str, replacement_map: dict[str, str]) -> str:
    """
    Restore original PII values from typed placeholders.

    Args:
        masked_text: Text with [TYPE_N] placeholders.
        replacement_map: Mapping from placeholder to original value.

    Returns:
        Text with PII restored.
    """
    result = masked_text
    # Sort by placeholder length descending to avoid partial replacements
    for placeholder, original in sorted(
        replacement_map.items(), key=lambda x: len(x[0]), reverse=True
    ):
        result = result.replace(placeholder, original)
    return result
