"""
FreeRelay — Hedged Execution (§13)
====================================
Speculative parallel execution with early cancellation.
Fire the same request at top 2 providers simultaneously.
Return whichever responds first. Cancel the other.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider

logger = logging.getLogger("freerelay.hedging")


async def hedged_execute(
    providers: list[tuple[BaseProvider, str]],
    request: ChatCompletionRequest,
) -> tuple[ChatCompletionResponse, str]:
    """
    Fire the same request at up to 2 providers in parallel.
    Return the response and the name of the winning provider.

    Args:
        providers: List of (provider, api_key) tuples, max 2.
        request: The chat completion request.

    Returns:
        Tuple of (response, winner_name) from the fastest provider.

    Raises:
        Exception: If all providers fail.
    """
    if not providers:
        raise ValueError("No providers for hedged execution")

    # Limit to 2 providers
    targets = providers[:2]

    tasks: dict[asyncio.Task[ChatCompletionResponse], BaseProvider] = {
        asyncio.create_task(provider.complete(request, api_key)): provider
        for provider, api_key in targets
    }

    done, pending = await asyncio.wait(
        tasks.keys(),
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Cancel all pending tasks immediately
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    # Check all done tasks for a successful result
    # done may contain 1 or 2 tasks (both completed before cancellation)
    errors: list[BaseException] = []
    for task in done:
        if task.exception() is None:
            winner = tasks[task]
            logger.info("Hedged winner: %s", winner.name)
            return task.result(), winner.name
        errors.append(task.exception())  # type: ignore[arg-type]

    # All done tasks failed
    logger.warning("All hedged providers failed (%d errors)", len(errors))
    raise errors[0]
