"""
FreeRelay — Chaos Engineering (§Chaos Mode)
==============================================
Injects failures, latency spikes, and rate limit responses
for testing application resilience.
"""

from __future__ import annotations

import asyncio
import random

from freerelay.providers.base import ProviderError, RateLimitError


class ChaosInjector:
    """
    Chaos engineering layer.

    When enabled, randomly:
    - Injects 429 rate limit errors
    - Adds latency spikes (500ms-3s)
    - Returns 500 server errors
    - Drops connections (timeout)

    Intensity controls the probability (0.0 = never, 1.0 = always).
    """

    def __init__(
        self,
        enabled: bool = False,
        intensity: float = 0.1,
        forced_scenario: str | None = None,
    ) -> None:
        self.enabled = enabled
        self.intensity = max(0.0, min(1.0, intensity))
        self.forced_scenario = forced_scenario

    async def maybe_inject(self, provider_name: str) -> None:
        """
        Call before each provider request.
        Raises an exception or adds delay with probability = intensity.
        """
        if not self.enabled:
            return

        if random.random() > self.intensity:
            return

        # Pick a chaos scenario
        scenario = self.forced_scenario or random.choice(
            [
                "rate_limit",
                "server_error",
                "latency_spike",
                "timeout",
            ]
        )

        if scenario == "rate_limit":
            raise RateLimitError(
                message=f"[CHAOS] Injected 429 for {provider_name}",
                provider_name=provider_name,
            )

        if scenario == "server_error":
            raise ProviderError(
                message=f"[CHAOS] Injected 500 for {provider_name}",
                status_code=500,
                provider_name=provider_name,
                retryable=True,
            )

        if scenario == "latency_spike":
            delay = random.uniform(0.5, 3.0)
            await asyncio.sleep(delay)

        if scenario == "timeout":
            raise ProviderError(
                message=f"[CHAOS] Injected timeout for {provider_name}",
                status_code=504,
                provider_name=provider_name,
                retryable=True,
            )
