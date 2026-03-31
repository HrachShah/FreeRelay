"""
FreeRelay — Internal Canonical Request Format
================================================
Wraps the OpenAI request with FreeRelay-specific metadata
used by routing, caching, telemetry, and budget tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from freerelay.core.models.openai import ChatCompletionRequest


@dataclass
class InternalRequest:
    """
    Internal representation of a chat completion request.
    Wraps the original OpenAI request with routing metadata.
    """

    # ── Original request ──────────────────────────────────
    openai_request: ChatCompletionRequest

    # ── FreeRelay metadata ────────────────────────────────
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:16]}")
    namespace: str = "default"
    created_at: float = field(default_factory=time.time)

    # ── Classification (set by classifier) ────────────────
    intent: str = "general"  # coding/math/chat/creative/multilingual/general
    estimated_tokens: int = 0

    # ── Routing hints ─────────────────────────────────────
    latency_critical: bool = False  # enables hedging
    preferred_provider: str | None = None

    # ── Cache ─────────────────────────────────────────────
    cache_hit: bool = False
    cache_key: str | None = None

    # ── Compression ───────────────────────────────────────
    compression_ratio: float = 1.0
    tokens_saved: int = 0

    # ── Result metadata (set after execution) ─────────────
    selected_provider: str = ""
    latency_ms: float = 0.0
    circuit_state: str = "CLOSED"
    budget_remaining_ratio: float = 1.0

    def elapsed_ms(self) -> float:
        """Milliseconds since request creation."""
        return (time.time() - self.created_at) * 1000

    def to_log_dict(self) -> dict[str, object]:
        """Structured log fields per spec §16.3."""
        return {
            "request_id": self.request_id,
            "namespace": self.namespace,
            "intent": self.intent,
            "provider": self.selected_provider,
            "model": self.openai_request.model,
            "latency_ms": round(self.latency_ms, 1),
            "tokens_prompt": self.estimated_tokens,
            "cache_hit": self.cache_hit,
            "compression_ratio": round(self.compression_ratio, 2),
            "circuit_state": self.circuit_state,
            "budget_remaining_ratio": round(self.budget_remaining_ratio, 2),
            "streaming": self.openai_request.is_streaming(),
        }
