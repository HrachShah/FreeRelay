"""
FreeRelay — Prometheus Metrics (§16.1)
========================================
Metrics registry with all counters, histograms, and gauges from the spec.
"""

from __future__ import annotations

__all__ = [
    "PROMETHEUS_AVAILABLE",
    "CONTENT_TYPE_LATEST",
    "generate_latest",
    "requests_total",
    "request_duration",
    "tokens_used",
    "cache_hits",
    "circuit_state",
    "budget_remaining",
    "compression_ratio",
]

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    requests_total = Counter(
        "freerelay_requests_total",
        "Total requests processed",
        ["provider", "status", "intent"],
    )

    request_duration = Histogram(
        "freerelay_request_duration_seconds",
        "End-to-end request latency",
        ["provider", "cached"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    )

    tokens_used = Counter(
        "freerelay_tokens_used_total",
        "Token usage",
        ["provider", "direction"],  # direction: prompt | completion
    )

    cache_hits = Counter(
        "freerelay_cache_hits_total",
        "Semantic cache hits",
    )

    circuit_state = Gauge(
        "freerelay_circuit_state",
        "Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
        ["provider"],
    )

    budget_remaining = Gauge(
        "freerelay_budget_remaining_ratio",
        "Remaining budget ratio 0.0-1.0",
        ["provider"],
    )

    compression_ratio = Histogram(
        "freerelay_compression_ratio",
        "Prompt compression effectiveness",
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )

    PROMETHEUS_AVAILABLE = True

except ImportError:
    PROMETHEUS_AVAILABLE = False

    # Stubs so code doesn't break without prometheus-client
    class _StubMetric:
        def labels(self, *args: object, **kwargs: object) -> _StubMetric:
            return self
        def inc(self, *args: object) -> None: pass
        def set(self, *args: object) -> None: pass
        def observe(self, *args: object) -> None: pass

    requests_total = _StubMetric()  # type: ignore[assignment]
    request_duration = _StubMetric()  # type: ignore[assignment]
    tokens_used = _StubMetric()  # type: ignore[assignment]
    cache_hits = _StubMetric()  # type: ignore[assignment]
    circuit_state = _StubMetric()  # type: ignore[assignment]
    budget_remaining = _StubMetric()  # type: ignore[assignment]
    compression_ratio = _StubMetric()  # type: ignore[assignment]

    def generate_latest() -> bytes:  # type: ignore[misc]
        return b""

    CONTENT_TYPE_LATEST = "text/plain"
