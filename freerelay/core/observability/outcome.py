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
    selected_provider: str
    alternatives: list[str]
    success: bool
    schema_pass: bool | None
    latency_ms: float
    cost_tokens: int
    hallucination_signal: float
    downstream_success: str | None
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
