"""
Tests — Circuit Breaker
=========================
Verify all state transitions per spec §9.
"""

import asyncio

import pytest

from freerelay.core.resilience.circuit_breaker import CircuitBreaker, CircuitState


@pytest.fixture
def breaker() -> CircuitBreaker:
    return CircuitBreaker(
        provider_name="test",
        failure_threshold=3,
        failure_window=60,
        recovery_timeout=1,  # 1 second for fast tests
    )


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_starts_closed(self, breaker: CircuitBreaker) -> None:
        assert breaker.state == CircuitState.CLOSED
        assert await breaker.can_execute()

    @pytest.mark.asyncio
    async def test_stays_closed_below_threshold(self, breaker: CircuitBreaker) -> None:
        await breaker.record_failure(500)
        await breaker.record_failure(502)
        assert breaker.state == CircuitState.CLOSED
        assert await breaker.can_execute()

    @pytest.mark.asyncio
    async def test_opens_at_threshold(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            await breaker.record_failure(500)
        assert breaker.state == CircuitState.OPEN
        assert not await breaker.can_execute()

    @pytest.mark.asyncio
    async def test_429_counts_as_failure(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            await breaker.record_failure(429)
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_400_does_not_count(self, breaker: CircuitBreaker) -> None:
        """Client errors (400, 401, 403) must not trip the breaker (§9.3)."""
        for _ in range(10):
            await breaker.record_failure(400)
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_401_does_not_count(self, breaker: CircuitBreaker) -> None:
        for _ in range(10):
            await breaker.record_failure(401)
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(
        self, breaker: CircuitBreaker
    ) -> None:
        for _ in range(3):
            await breaker.record_failure(500)
        assert breaker.state == CircuitState.OPEN

        await asyncio.sleep(1.1)
        assert breaker.state == CircuitState.HALF_OPEN  # type: ignore[comparison-overlap]
        assert await breaker.can_execute()

    @pytest.mark.asyncio
    async def test_allows_only_one_half_open_probe(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            await breaker.record_failure(500)
        await asyncio.sleep(1.1)

        assert await breaker.can_execute()
        assert not await breaker.can_execute()

        await breaker.record_success()
        assert await breaker.can_execute()

    @pytest.mark.asyncio
    async def test_half_open_failure_releases_probe(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            await breaker.record_failure(500)
        await asyncio.sleep(1.1)

        assert await breaker.can_execute()
        await breaker.record_failure(500)
        assert not await breaker.can_execute()

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(
        self, breaker: CircuitBreaker
    ) -> None:
        for _ in range(3):
            await breaker.record_failure(500)
        await asyncio.sleep(1.1)
        assert breaker.state == CircuitState.HALF_OPEN  # type: ignore[comparison-overlap]

        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED  # type: ignore[comparison-overlap]

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            await breaker.record_failure(500)
        await asyncio.sleep(1.1)
        assert breaker.state == CircuitState.HALF_OPEN  # type: ignore[comparison-overlap]

        await breaker.record_failure(500)
        assert breaker.state == CircuitState.OPEN  # type: ignore[comparison-overlap]

    @pytest.mark.asyncio
    async def test_none_status_counts_as_failure(self, breaker: CircuitBreaker) -> None:
        """Timeout/connection errors (None status) count as failures."""
        for _ in range(3):
            await breaker.record_failure(None)
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_scoring(self, breaker: CircuitBreaker) -> None:
        assert breaker.get_score() == 1.0

        for _ in range(3):
            await breaker.record_failure(500)
        assert breaker.get_score() == 0.0

        await asyncio.sleep(1.1)
        assert breaker.get_score() == 0.5
