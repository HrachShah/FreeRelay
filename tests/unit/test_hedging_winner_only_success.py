"""
Tests — Hedged execution only records circuit-breaker success on the winner.

The hedged execution path fires a request at two providers in parallel
and returns whichever responds first. The losing provider either gets
cancelled mid-flight or completes after the winner — either way it did
NOT successfully serve the user, so its circuit breaker must NOT be
reset to CLOSED. Only the winner's circuit should record success.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from freerelay.core.execution.executor import Executor
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    Message,
)
from freerelay.core.resilience.circuit_breaker import CircuitBreaker, CircuitState


def _make_provider(name: str, delay: float, fail: bool = False) -> MagicMock:
    provider = MagicMock()
    provider.name = name

    async def _complete(request, api_key):
        await asyncio.sleep(delay)
        if fail:
            raise RuntimeError(f"{name} boom")
        return ChatCompletionResponse(
            id=f"resp-{name}",
            created=0,
            model=f"model-{name}",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=f"{name}-wins"),
                    finish_reason="stop",
                )
            ],
        )

    provider.complete = _complete
    return provider


def _make_request() -> ChatCompletionRequest:
    req = MagicMock(spec=ChatCompletionRequest)
    req.model = "test-model"
    req.messages = []
    return req


@pytest.mark.asyncio
async def test_hedged_winner_records_success_only_on_winner() -> None:
    """Provider A is faster; A's circuit becomes CLOSED but B's stays OPEN
    because B was cancelled mid-flight (its request never completed)."""
    a_breaker = CircuitBreaker(
        provider_name="a", failure_threshold=3, failure_window=60, recovery_timeout=0.5
    )
    b_breaker = CircuitBreaker(
        provider_name="b", failure_threshold=3, failure_window=60, recovery_timeout=0.5
    )
    # Pre-open both circuits with 3 failures to mimic a struggling provider.
    for _ in range(3):
        await a_breaker.record_failure(500)
        await b_breaker.record_failure(500)
    assert a_breaker.state == CircuitState.OPEN
    assert b_breaker.state == CircuitState.OPEN

    # Wait past the recovery window so the auto-transition can fire when
    # record_success is called.
    await asyncio.sleep(0.6)

    a = _make_provider("A", delay=0.05)
    b = _make_provider("B", delay=0.50)  # loser (will be cancelled)
    executor = Executor(enable_hedging=True, max_retries=0)
    result = await executor.execute_hedged(
        [(a, "key-a", a_breaker), (b, "key-b", b_breaker)],
        _make_request(),
    )

    assert result.choices[0].message.content == "A-wins"
    # The winner's circuit went OPEN → HALF_OPEN → CLOSED with failures cleared.
    assert a_breaker.state == CircuitState.CLOSED, (
        f"winner A should have success recorded and circuit reset to CLOSED, got {a_breaker.state}"
    )
    assert a_breaker.get_score() == 1.0
    # The loser's circuit was NOT marked successful.
    # It auto-transitioned to HALF_OPEN during the sleep, but the loser's task
    # was cancelled, so no failure was recorded — the circuit should remain
    # HALF_OPEN (a probe slot is still open for it to retry). It must NOT
    # be CLOSED, because that would mean we silently treated the loser as healthy.
    assert b_breaker.state != CircuitState.CLOSED, (
        f"loser B must NOT be marked successful; got {b_breaker.state}"
    )


@pytest.mark.asyncio
async def test_hedged_all_fail_records_failure_on_both() -> None:
    """When every provider fails, every circuit breaker should see the failure."""
    a = _make_provider("A", delay=0.01, fail=True)
    b = _make_provider("B", delay=0.02, fail=True)
    circuit_a = CircuitBreaker("A", failure_threshold=5)
    circuit_b = CircuitBreaker("B", failure_threshold=5)
    executor = Executor(enable_hedging=True, max_retries=0)
    with pytest.raises(RuntimeError):
        await executor.execute_hedged(
            [(a, "key-a", circuit_a), (b, "key-b", circuit_b)],
            _make_request(),
        )

    # Both should still be CLOSED (threshold=5, only 1 failure each)
    assert circuit_a.state == CircuitState.CLOSED
    assert circuit_b.state == CircuitState.CLOSED
