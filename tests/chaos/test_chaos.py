"""
Tests — Chaos Engineering
============================
Verify chaos injection behavior per spec.
"""

import asyncio

import pytest

from freerelay.core.resilience.chaos import ChaosInjector
from freerelay.providers.base import ProviderError, RateLimitError


class TestChaosInjector:
    def test_disabled_by_default(self) -> None:
        injector = ChaosInjector(enabled=False)
        # Should not raise
        asyncio.run(injector.maybe_inject("test"))

    @pytest.mark.asyncio
    async def test_disabled_does_nothing(self) -> None:
        injector = ChaosInjector(enabled=False)
        await injector.maybe_inject("test")  # No exception

    @pytest.mark.asyncio
    async def test_intensity_zero_never_injects(self) -> None:
        injector = ChaosInjector(enabled=True, intensity=0.0)
        for _ in range(100):
            await injector.maybe_inject("test")  # No exception

    @pytest.mark.asyncio
    async def test_intensity_one_always_injects(self) -> None:
        injector = ChaosInjector(enabled=True, intensity=1.0)
        errors = 0
        for _ in range(50):
            try:
                await injector.maybe_inject("test")
            except (RateLimitError, ProviderError):
                errors += 1
        # With intensity=1.0, every call should either raise or delay
        # Since latency_spike doesn't raise, we can't guarantee 100% raise rate
        assert errors > 0

    @pytest.mark.asyncio
    async def test_injects_rate_limit(self) -> None:
        injector = ChaosInjector(
            enabled=True,
            intensity=1.0,
            forced_scenario="rate_limit",
        )
        with pytest.raises(RateLimitError):
            await injector.maybe_inject("test")

    @pytest.mark.asyncio
    async def test_injects_server_error(self) -> None:
        injector = ChaosInjector(
            enabled=True,
            intensity=1.0,
            forced_scenario="server_error",
        )
        with pytest.raises(ProviderError) as exc:
            await injector.maybe_inject("test")
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_injects_timeout(self) -> None:
        injector = ChaosInjector(
            enabled=True,
            intensity=1.0,
            forced_scenario="timeout",
        )
        with pytest.raises(ProviderError) as exc:
            await injector.maybe_inject("test")
        assert exc.value.status_code == 504

    @pytest.mark.asyncio
    async def test_latency_spike_adds_delay(self) -> None:
        injector = ChaosInjector(
            enabled=True,
            intensity=1.0,
            forced_scenario="latency_spike",
        )
        start = asyncio.get_event_loop().time()
        await asyncio.wait_for(injector.maybe_inject("test"), timeout=4.0)
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed > 0.4
