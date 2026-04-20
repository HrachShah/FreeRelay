"""
Tests — Provider Scorer
==========================
Verify composite scoring functions per spec §14.1.
"""

import pytest

from freerelay.core.models.capability import CapabilityMatrix, ModelCapability
from freerelay.core.resilience.budget import BudgetForecaster
from freerelay.core.resilience.circuit_breaker import CircuitBreaker
from freerelay.core.routing.scorer import (
    compute_capability_score,
    compute_composite_score,
    compute_latency_score,
)


class TestCapabilityScore:
    def test_default_without_matrix(self) -> None:
        score = compute_capability_score("groq", "coding", None)
        assert score == 0.8

    def test_no_models_for_provider(self) -> None:
        matrix = CapabilityMatrix()
        score = compute_capability_score("unknown", "coding", matrix)
        assert score == 0.3

    def test_strength_match(self) -> None:
        matrix = CapabilityMatrix(
            models={
                "groq/llama-70b": ModelCapability(
                    provider="groq",
                    strengths=["coding", "reasoning"],
                    weaknesses=[],
                ),
            }
        )
        score = compute_capability_score("groq", "coding", matrix)
        assert score == 0.95

    def test_no_match_no_weakness(self) -> None:
        matrix = CapabilityMatrix(
            models={
                "groq/llama-70b": ModelCapability(
                    provider="groq",
                    strengths=["reasoning"],
                    weaknesses=["math"],
                ),
            }
        )
        score = compute_capability_score("groq", "coding", matrix)
        assert score == 0.7

    def test_weakness_match(self) -> None:
        matrix = CapabilityMatrix(
            models={
                "groq/llama-70b": ModelCapability(
                    provider="groq",
                    strengths=["reasoning"],
                    weaknesses=["math"],
                ),
            }
        )
        score = compute_capability_score("groq", "math", matrix)
        assert score == 0.4


class TestLatencyScore:
    def test_zero_latency(self) -> None:
        score = compute_latency_score(0.0)
        assert score == 1.0

    def test_1000ms_latency(self) -> None:
        score = compute_latency_score(1000.0)
        assert score == 0.5

    def test_high_latency(self) -> None:
        score = compute_latency_score(9000.0)
        assert score == pytest.approx(0.1, abs=0.01)

    def test_score_decreases_with_latency(self) -> None:
        s1 = compute_latency_score(100.0)
        s2 = compute_latency_score(500.0)
        s3 = compute_latency_score(1000.0)
        assert s1 > s2 > s3


class TestCompositeScore:
    @pytest.mark.asyncio
    async def test_all_good(self) -> None:
        cb = CircuitBreaker("test")
        budget = BudgetForecaster()
        score = await compute_composite_score(
            "test",
            "coding",
            cb,
            budget,
            0.0,
        )
        assert score == 0.8  # capability default

    @pytest.mark.asyncio
    async def test_open_circuit_zeroes_score(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1)
        await cb.record_failure(500)
        budget = BudgetForecaster()
        score = await compute_composite_score(
            "test",
            "coding",
            cb,
            budget,
            100.0,
        )
        assert score == 0.0


import pytest
