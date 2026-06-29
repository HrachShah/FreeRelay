"""
FreeRelay — Stacked token compression middleware (Phase 2).

Three composable engines, applied in order:
  1. RTK   — strips tool-call/command output noise (shells out to rtk binary)
  2. Caveman — deterministic prose simplification rules (~0ms, safe in hot path)
  3. LLMLingua-2 — neural compression (200-800ms on CPU; OPT-IN ONLY via route config)

Usage (from FastAPI middleware or route handler):
    from freerelay.middleware.compression import compress_messages
    messages = compress_messages(messages, engines=["rtk", "caveman"])

The compress_messages() function is pure (no I/O side-effects on the request).
Token savings are returned alongside the result so callers can emit telemetry headers.

# ponytail: LLMLingua runs async in a threadpool — it's never in the sync hot path
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Sequence


# ── data types ───────────────────────────────────────────────────────────────

@dataclass
class CompressionResult:
    messages: list[dict]
    original_chars: int
    compressed_chars: int
    engines_applied: list[str] = field(default_factory=list)

    @property
    def savings_pct(self) -> float:
        if self.original_chars == 0:
            return 0.0
        return (1 - self.compressed_chars / self.original_chars) * 100


# ── RTK engine ───────────────────────────────────────────────────────────────

def _rtk_compress_text(text: str) -> str:
    """Shell out to rtk binary to filter command/tool output noise."""
    rtk = shutil.which("rtk")
    if not rtk:
        return text
    try:
        result = subprocess.run(
            [rtk, "compress"],
            input=text,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout if result.returncode == 0 else text
    except Exception:
        return text


def apply_rtk(messages: list[dict]) -> list[dict]:
    """Apply RTK compression to tool/assistant messages with heavy command output."""
    out = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("tool", "assistant") and isinstance(content, str) and len(content) > 500:
            content = _rtk_compress_text(content)
        out.append({**msg, "content": content})
    return out


# ── Caveman engine ────────────────────────────────────────────────────────────
#
# Deterministic prose rules ported from OmniRoute's Caveman spec.
# These are cheap (~0ms) and safe for the default hot path.
# Rules: remove filler phrases, redundant politeness, padding words.

_CAVEMAN_RULES: list[tuple[re.Pattern, str]] = [
    # filler openings
    (re.compile(r"(?i)^(certainly|absolutely|of course|sure)[,!.]?\s*", re.MULTILINE), ""),
    (re.compile(r"(?i)^(great question|good question)[.!]?\s*", re.MULTILINE), ""),
    (re.compile(r"(?i)^(I'd be happy to help|I'd be glad to|I'll help you)[.!]?\s*", re.MULTILINE), ""),
    (re.compile(r"(?i)^(I understand (that|your|the)|I see that)\s*", re.MULTILINE), ""),
    # closing padding
    (re.compile(r"(?i)(Is there anything else I can (help|assist) (you with|you today)[?.]?\s*)$", re.MULTILINE), ""),
    (re.compile(r"(?i)(Feel free to (let me know|ask)[^.]*[.!]?\s*)$", re.MULTILINE), ""),
    (re.compile(r"(?i)(Please (let me know|feel free)[^.]*[.!]?\s*)$", re.MULTILINE), ""),
    # excessive whitespace (collapse 3+ newlines → 2)
    (re.compile(r"\n{3,}"), "\n\n"),
    # trailing whitespace per line
    (re.compile(r"[ \t]+$", re.MULTILINE), ""),
]


def _caveman_compress_text(text: str) -> str:
    for pattern, replacement in _CAVEMAN_RULES:
        text = pattern.sub(replacement, text)
    return text.strip()


def apply_caveman(messages: list[dict]) -> list[dict]:
    """Apply Caveman deterministic prose rules to all text messages."""
    out = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            content = _caveman_compress_text(content)
        out.append({**msg, "content": content})
    return out


# ── LLMLingua-2 engine (opt-in, async) ───────────────────────────────────────

_llmlingua_available: bool | None = None  # None = unchecked


def _check_llmlingua() -> bool:
    global _llmlingua_available
    if _llmlingua_available is None:
        try:
            import llmlingua  # noqa: F401
            _llmlingua_available = True
        except ImportError:
            _llmlingua_available = False
    return _llmlingua_available


def _llmlingua_compress_sync(text: str, ratio: float = 0.5) -> str:
    """Blocking LLMLingua-2 compression — call from a threadpool."""
    if not _check_llmlingua():
        return text
    try:
        from llmlingua import PromptCompressor  # type: ignore
        compressor = PromptCompressor(model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank")
        result = compressor.compress_prompt(text, rate=ratio)
        return result.get("compressed_prompt", text)
    except Exception:
        return text


async def apply_llmlingua(messages: list[dict], ratio: float = 0.5) -> list[dict]:
    """Apply LLMLingua-2 neural compression (async, runs in threadpool)."""
    loop = asyncio.get_event_loop()
    out = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 200:
            content = await loop.run_in_executor(
                None, _llmlingua_compress_sync, content, ratio
            )
        out.append({**msg, "content": content})
    return out


# ── Public API ────────────────────────────────────────────────────────────────

async def compress_messages(
    messages: list[dict],
    engines: Sequence[str] = ("caveman",),
) -> CompressionResult:
    """
    Apply requested compression engines in order and return a CompressionResult.

    engines: ordered list of "rtk", "caveman", "llmlingua"
    Default: only caveman (cheap, deterministic, safe for hot path).
    "rtk" and "llmlingua" opt-in via route config.
    """
    original_chars = sum(len(m.get("content", "") or "") for m in messages)
    applied: list[str] = []
    msgs = list(messages)

    for engine in engines:
        if engine == "rtk":
            msgs = apply_rtk(msgs)
            applied.append("rtk")
        elif engine == "caveman":
            msgs = apply_caveman(msgs)
            applied.append("caveman")
        elif engine == "llmlingua":
            msgs = await apply_llmlingua(msgs)
            applied.append("llmlingua")

    compressed_chars = sum(len(m.get("content", "") or "") for m in msgs)
    return CompressionResult(
        messages=msgs,
        original_chars=original_chars,
        compressed_chars=compressed_chars,
        engines_applied=applied,
    )


# ── self-check ────────────────────────────────────────────────────────────────

def demo() -> None:
    """Assert-based self-check: confirm token count drops and round-trips semantically."""
    import asyncio

    sample = [
        {"role": "user", "content": "Certainly! Great question. I'd be happy to help you understand this.\n\nThe answer is 42.\n\nIs there anything else I can help you with?"},
        {"role": "assistant", "content": "Sure, absolutely! Of course. Here is the result:\n\n```\noutput line 1\noutput line 2\n```\n\nFeel free to let me know if you need more help!"},
    ]

    result = asyncio.run(compress_messages(sample, engines=["caveman"]))

    assert result.compressed_chars < result.original_chars, "Caveman should reduce char count"
    assert result.savings_pct > 0, "Savings should be > 0"
    assert "caveman" in result.engines_applied
    assert "42" in result.messages[0]["content"], "Key content must survive compression"
    print(f"Caveman: {result.original_chars} -> {result.compressed_chars} chars ({result.savings_pct:.1f}% saved)")
    print("Self-check PASSED")


if __name__ == "__main__":
    demo()
