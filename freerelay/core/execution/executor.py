"""
FreeRelay — Execution Orchestrator (§11-13)
=============================================
Orchestrates request execution with retry, hedging, and fallback.
Wraps the provider call with all resilience layers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from freerelay.core.execution.hedging import hedged_execute
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.core.resilience.circuit_breaker import CircuitBreaker
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError

logger = logging.getLogger("freerelay.executor")


class Executor:
    """
    Request execution orchestrator.

    Handles:
    - Single provider execution with retry
    - Hedged execution (parallel to top 2 providers)
    - Circuit breaker integration
    - Latency tracking
    """

    def __init__(
        self,
        enable_hedging: bool = False,
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 5.0,
    ) -> None:
        self.enable_hedging = enable_hedging
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay

    async def execute(
        self,
        provider: BaseProvider,
        request: ChatCompletionRequest,
        api_key: str,
        circuit: CircuitBreaker | None = None,
    ) -> ChatCompletionResponse:
        """
        Execute a request against a single provider with retry.

        Args:
            provider: The provider to execute against.
            request: The chat completion request.
            api_key: API key for the provider.
            circuit: Optional circuit breaker to update.

        Returns:
            ChatCompletionResponse from the provider.

        Raises:
            ProviderError: If all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                start = time.time()
                response = await provider.complete(request, api_key)
                elapsed_ms = (time.time() - start) * 1000

                if circuit:
                    await circuit.record_success()

                logger.info(
                    "%s succeeded on attempt %d (%.0fms)",
                    provider.name,
                    attempt + 1,
                    elapsed_ms,
                )
                return response

            except RateLimitError as e:
                last_error = e
                if circuit:
                    await circuit.record_failure(429)
                if attempt < self.max_retries:
                    delay = min(
                        self.retry_base_delay * (2**attempt),
                        self.retry_max_delay,
                    )
                    logger.warning(
                        "%s rate limited, retrying in %.1fs (attempt %d)",
                        provider.name,
                        delay,
                        attempt + 1,
                    )
                    await asyncio.sleep(delay)
                continue

            except ProviderError as e:
                last_error = e
                if circuit:
                    await circuit.record_failure(e.status_code)
                if not e.retryable or attempt >= self.max_retries:
                    raise
                delay = min(
                    self.retry_base_delay * (2**attempt),
                    self.retry_max_delay,
                )
                logger.warning(
                    "%s error %d, retrying in %.1fs (attempt %d)",
                    provider.name,
                    e.status_code,
                    delay,
                    attempt + 1,
                )
                await asyncio.sleep(delay)
                continue

            except Exception as e:
                last_error = e
                if circuit:
                    await circuit.record_failure(None)
                raise

        raise last_error or ProviderError("All retries exhausted")

    async def execute_hedged(
        self,
        providers: list[tuple[BaseProvider, str, CircuitBreaker]],
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """
        Execute with hedging — fire at top 2 providers in parallel.

        Args:
            providers: List of (provider, api_key, circuit_breaker) tuples.
            request: The chat completion request.

        Returns:
            Response from the fastest provider.
        """
        provider_keys = [(p, k) for p, k, _ in providers]
        circuits = {p.name: c for p, _, c in providers}
        try:
            response = await hedged_execute(provider_keys, request)
            # Record success on the circuit breaker of whichever provider won
            for _name, circuit in circuits.items():
                await circuit.record_success()
            return response
        except Exception as e:
            # Record failure on all involved circuit breakers
            for _name, circuit in circuits.items():
                status = e.status_code if isinstance(e, ProviderError) else None
                await circuit.record_failure(status)
            raise

    async def execute_stream(
        self,
        provider: BaseProvider,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        """
        Execute a streaming request.

        Args:
            provider: The provider to execute against.
            request: The chat completion request.
            api_key: API key for the provider.

        Yields:
            SSE lines from the provider.
        """
        async for line in provider.stream(request, api_key):
            yield line
