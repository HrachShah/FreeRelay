"""
FreeRelay — Shared Capability Models (§10.1)
=============================================
Models for provider capability tracking, bandit arms,
budget forecasting, and circuit breaker state.
"""

from __future__ import annotations

import enum
import time

from pydantic import BaseModel, Field

# ─── CircuitState (§10.2) ────────────────────────────────────────────────────


class CircuitState(enum.StrEnum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ─── CapabilityRecord (§10.1) ────────────────────────────────────────────────


class CapabilityRecord(BaseModel):
    """
    Measured capability profile for a single provider/model pair.
    Updated by the benchmark and learner components.
    """

    provider: str = ""
    model: str = ""
    last_benchmarked_ts: float = Field(default_factory=time.time)

    # ── Context ──────────────────────────────────────────────────────────────
    context_window_claimed: int = 8192
    context_window_tested: int = 8192

    # ── Latency ──────────────────────────────────────────────────────────────
    p50_ttft_ms: float = 0.0
    p95_ttft_ms: float = 0.0
    p99_ttft_ms: float = 0.0
    p50_total_ms: float = 0.0
    p95_total_ms: float = 0.0
    tokens_per_second_median: float = 0.0
    timeout_rate: float = 0.0

    # ── Quality ──────────────────────────────────────────────────────────────
    quality_by_task_family: dict[str, float] = Field(default_factory=dict)
    schema_compliance_rate: float = 0.0
    tool_call_accuracy: float = 0.0
    long_context_recall_32k: float = 0.0
    long_context_recall_64k: float = 0.0
    long_context_recall_128k: float = 0.0
    code_test_pass_rate: float = 0.0
    multilingual_scores: dict[str, float] = Field(default_factory=dict)
    streaming_chunk_cv: float = 0.0
    refusal_rate_permissive: float = 0.0

    # ── Features ─────────────────────────────────────────────────────────────
    streaming_available: bool = True
    tools_available: bool = False
    json_mode_available: bool = False
    vision_available: bool = False
    logprobs_available: bool = False

    # ── Degradation ──────────────────────────────────────────────────────────
    streaming_degraded: bool = False
    tools_degraded: bool = False
    json_mode_degraded_above_tokens: int = 0
    latency_degraded: bool = False
    drift_detected: bool = False

    # ── Economics ────────────────────────────────────────────────────────────
    cost_per_prompt_token: float = 0.0
    cost_per_completion_token: float = 0.0
    is_free_tier: bool = True

    # ── Quota ────────────────────────────────────────────────────────────────
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    tpd_limit: int | None = None
    prior_quality: float = 0.5


# ─── BanditArm ───────────────────────────────────────────────────────────────


class BanditArm(BaseModel):
    """UCB/Thompson bandit arm tracking quality estimates per provider/model/task."""

    provider: str = ""
    model: str = ""
    task_family: str = ""

    mean_quality: float = 0.0
    n_pulls: int = 0
    sum_quality: float = 0.0
    ewma_quality: float = 0.0
    variance: float = 0.0
    m2: float = 0.0  # Welford's algorithm accumulator
    last_updated_ts: float = Field(default_factory=time.time)


# ─── BudgetForecast ──────────────────────────────────────────────────────────


class BudgetForecast(BaseModel):
    """Budget usage forecast for a provider key."""

    provider: str = ""
    key_hash: str = ""

    remaining_ratio: float = 1.0
    budget_warning: bool = False
    budget_exhausted: bool = False

    ewma_rate: float = 0.0  # tokens per second (EWMA)
    tokens_today: int = 0
    projected_total: int = 0
    reset_ts: float = 0.0


# ─── CircuitBreakerState (§10.2) ─────────────────────────────────────────────


class CircuitBreakerState(BaseModel):
    """State of a per-provider circuit breaker."""

    provider: str = ""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_ts: float = 0.0
    open_since_ts: float = 0.0
    probe_in_flight: bool = False


# ─── FreeTierLimits ──────────────────────────────────────────────────────────


class FreeTierLimits(BaseModel):
    """Free tier rate limits and costs for a provider."""

    provider: str = ""
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    tpd_limit: int | None = None
    daily_token_limit: int | None = None
    cost_per_prompt_token: float = 0.0
    cost_per_completion_token: float = 0.0
