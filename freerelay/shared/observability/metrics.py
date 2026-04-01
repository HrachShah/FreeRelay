"""
FreeRelay — Prometheus Metrics Registry (§15.1)
=================================================
Complete metrics registry with all 20 counters, histograms, and gauges
from the spec, plus helper functions for common operations.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


# ─── Stub for when prometheus-client is not installed ────────────────────────


class _StubMetric:
    """No-op metric stub so code doesn't break without prometheus-client."""

    def labels(self, *args: Any, **kwargs: Any) -> _StubMetric:
        return self

    def inc(self, *args: Any, **kwargs: Any) -> None:
        pass

    def dec(self, *args: Any, **kwargs: Any) -> None:
        pass

    def set(self, *args: Any, **kwargs: Any) -> None:
        pass

    def observe(self, *args: Any, **kwargs: Any) -> None:
        pass


# ─── Registry ────────────────────────────────────────────────────────────────


def _make_counter(name: str, desc: str, labels: list[str] | None = None) -> Any:
    if _PROMETHEUS_AVAILABLE:
        return Counter(name, desc, labels or [])
    return _StubMetric()


def _make_histogram(
    name: str,
    desc: str,
    labels: list[str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> Any:
    if _PROMETHEUS_AVAILABLE:
        kwargs: dict[str, Any] = {}
        if buckets is not None:
            kwargs["buckets"] = list(buckets)
        return Histogram(name, desc, labels or [], **kwargs)
    return _StubMetric()


def _make_gauge(name: str, desc: str, labels: list[str] | None = None) -> Any:
    if _PROMETHEUS_AVAILABLE:
        return Gauge(name, desc, labels or [])
    return _StubMetric()


# ─── All 20 Metrics (§15.1) ─────────────────────────────────────────────────

# 1. Total requests
requests_total: Any = _make_counter(
    "freerelay_requests_total",
    "Total requests processed",
    ["provider", "status", "intent"],
)

# 2. Request duration
request_duration_seconds: Any = _make_histogram(
    "freerelay_request_duration_seconds",
    "End-to-end request latency in seconds",
    ["provider", "cached"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

# 3. Time to first token
ttft_seconds: Any = _make_histogram(
    "freerelay_ttft_seconds",
    "Time to first token in seconds",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# 4. Tokens total
tokens_total: Any = _make_counter(
    "freerelay_tokens_total",
    "Total tokens consumed",
    ["provider", "direction"],  # direction: prompt | completion
)

# 5. Cache hits
cache_hits_total: Any = _make_counter(
    "freerelay_cache_hits_total",
    "Semantic cache hits",
    ["namespace"],
)

# 6. Circuit breaker state
circuit_state: Any = _make_gauge(
    "freerelay_circuit_state",
    "Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
    ["provider"],
)

# 7. Budget remaining ratio
budget_remaining_ratio: Any = _make_gauge(
    "freerelay_budget_remaining_ratio",
    "Remaining budget ratio 0.0-1.0",
    ["provider"],
)

# 8. Validation pass rate
validation_pass_rate: Any = _make_gauge(
    "freerelay_validation_pass_rate",
    "Validation pass rate 0.0-1.0",
    ["layer"],
)

# 9. Repair triggered
repair_triggered_total: Any = _make_counter(
    "freerelay_repair_triggered_total",
    "Number of times output repair was triggered",
    ["provider", "layer"],
)

# 10. Repair success rate
repair_success_rate: Any = _make_gauge(
    "freerelay_repair_success_rate",
    "Repair success rate 0.0-1.0",
    ["provider"],
)

# 11. Bandit arm quality
bandit_arm_quality: Any = _make_gauge(
    "freerelay_bandit_arm_quality",
    "Bandit arm mean quality estimate",
    ["provider", "model", "task_family"],
)

# 12. Bandit arm pulls
bandit_arm_pulls_total: Any = _make_counter(
    "freerelay_bandit_arm_pulls_total",
    "Total pulls per bandit arm",
    ["provider", "model", "task_family"],
)

# 13. Routing confidence gap
routing_confidence_gap: Any = _make_histogram(
    "freerelay_routing_confidence_gap",
    "Confidence gap between winner and runner-up",
    buckets=(0.0, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0),
)

# 14. DAG step duration
dag_step_duration_seconds: Any = _make_histogram(
    "freerelay_dag_step_duration_seconds",
    "Duration of individual DAG workflow steps",
    ["step_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# 15. Hallucination flags
hallucination_flags_total: Any = _make_counter(
    "freerelay_hallucination_flags_total",
    "Total hallucination flags detected",
    ["provider", "model"],
)

# 16. Compression ratio
compression_ratio: Any = _make_histogram(
    "freerelay_compression_ratio",
    "Prompt compression ratio (output/input)",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# 17. Brownout active
brownout_active: Any = _make_gauge(
    "freerelay_brownout_active",
    "Whether brownout shedding is active (1=yes, 0=no)",
    ["namespace"],
)

# 18. Benchmark score
benchmark_score: Any = _make_gauge(
    "freerelay_benchmark_score",
    "Latest benchmark score per provider/model/task",
    ["provider", "model", "task_family"],
)

# 19. Anomaly detected
anomaly_detected_total: Any = _make_counter(
    "freerelay_anomaly_detected_total",
    "Total anomalies detected by drift monitor",
    ["provider", "model", "anomaly_type"],
)

# 20. Agent steps
agent_steps_total: Any = _make_counter(
    "freerelay_agent_steps_total",
    "Total agent execution steps",
    ["provider", "status"],
)


# ─── Helper Functions ────────────────────────────────────────────────────────


def record_request(provider: str, status: str, intent: str = "general") -> None:
    """Record a completed request."""
    requests_total.labels(provider=provider, status=status, intent=intent).inc()


def record_latency(
    provider: str,
    duration_s: float,
    ttft_s: float = 0.0,
    cached: bool = False,
) -> None:
    """Record request latency and optionally TTFT."""
    request_duration_seconds.labels(provider=provider, cached=str(cached)).observe(
        duration_s
    )
    if ttft_s > 0:
        ttft_seconds.labels(provider=provider).observe(ttft_s)


def record_tokens(provider: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Record token usage."""
    tokens_total.labels(provider=provider, direction="prompt").inc(prompt_tokens)
    tokens_total.labels(provider=provider, direction="completion").inc(
        completion_tokens
    )


def record_cache_hit(namespace: str = "default") -> None:
    """Record a cache hit."""
    cache_hits_total.labels(namespace=namespace).inc()


def set_circuit_state(provider: str, state: int) -> None:
    """Set circuit breaker state gauge (0=CLOSED, 1=HALF_OPEN, 2=OPEN)."""
    circuit_state.labels(provider=provider).set(state)


def set_budget_remaining(provider: str, ratio: float) -> None:
    """Set remaining budget ratio for a provider."""
    budget_remaining_ratio.labels(provider=provider).set(ratio)


def record_validation(layer: str, passed: bool) -> None:
    """Update validation pass rate (caller should aggregate externally)."""
    validation_pass_rate.labels(layer=layer).set(1.0 if passed else 0.0)


def record_repair(provider: str, layer: str, success: bool) -> None:
    """Record a repair attempt."""
    repair_triggered_total.labels(provider=provider, layer=layer).inc()
    if success:
        repair_success_rate.labels(provider=provider).set(1.0)


def record_bandit_update(
    provider: str, model: str, task_family: str, quality: float, pulls: int
) -> None:
    """Update bandit arm metrics."""
    bandit_arm_quality.labels(
        provider=provider, model=model, task_family=task_family
    ).set(quality)
    bandit_arm_pulls_total.labels(
        provider=provider, model=model, task_family=task_family
    ).inc()


def record_routing_decision(confidence_gap: float) -> None:
    """Record routing confidence gap."""
    routing_confidence_gap.observe(confidence_gap)


def record_dag_step(step_name: str, duration_s: float) -> None:
    """Record DAG workflow step duration."""
    dag_step_duration_seconds.labels(step_name=step_name).observe(duration_s)


def record_hallucination(provider: str, model: str) -> None:
    """Record a hallucination flag."""
    hallucination_flags_total.labels(provider=provider, model=model).inc()


def record_compression(ratio: float) -> None:
    """Record compression ratio."""
    compression_ratio.observe(ratio)


def set_brownout(namespace: str, active: bool) -> None:
    """Set brownout shedding state."""
    brownout_active.labels(namespace=namespace).set(1 if active else 0)


def record_benchmark(provider: str, model: str, task_family: str, score: float) -> None:
    """Record a benchmark score."""
    benchmark_score.labels(provider=provider, model=model, task_family=task_family).set(
        score
    )


def record_anomaly(provider: str, model: str, anomaly_type: str) -> None:
    """Record a detected anomaly."""
    anomaly_detected_total.labels(
        provider=provider, model=model, anomaly_type=anomaly_type
    ).inc()


def record_agent_step(provider: str, status: str) -> None:
    """Record an agent execution step."""
    agent_steps_total.labels(provider=provider, status=status).inc()


def get_metrics_output() -> bytes:
    """
    Generate Prometheus exposition format output.
    Returns empty bytes if prometheus-client is not installed.
    """
    if _PROMETHEUS_AVAILABLE:
        return generate_latest()
    return b""
