"""
FreeRelay — Outcome Logger (§12)
======================================
Records post-hoc routing outcomes for learning, observability, and experimentation.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class OutcomeRecord:
    """Post-hoc information emitted after request resolution."""

    request_id: str
    user_id: str | None = None
    org_id: str | None = None
    selected_provider: str = ""
    model: str = ""
    alternatives: list[str] = field(default_factory=list)
    success: bool = False
    schema_pass: bool | None = None
    latency_ms: float = 0.0
    cost_tokens: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    cost_usd: float = 0.0
    baseline_cost_usd: float = 0.0
    savings_usd: float = 0.0
    hallucination_signal: float = 0.0
    downstream_success: str | None = None
    timestamp: float = field(default_factory=time.time)
    notes: str | None = None


class OutcomeLogger:
    """In-memory ring buffer of recent outcomes."""

    def __init__(self, max_records: int = 200) -> None:
        self._records: deque[OutcomeRecord] = deque(maxlen=max_records)

    def log(self, record: OutcomeRecord) -> None:
        self._records.append(record)

    def latest(self, count: int = 20) -> list[OutcomeRecord]:
        return list(self._records)[-count:]
