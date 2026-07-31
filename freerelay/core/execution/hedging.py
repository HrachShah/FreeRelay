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


class HedgedResult:
    """Result of a hedged execution, identifying which provider won."""

    __slots__ = ("response", "winner_name", "loser_names")

    def __init__(
        self,
        response: ChatCompletionResponse,
        winner_name: str,
        loser_names: tuple[str, ...],
    ) -> None:
        self.response = response
        self.winner_name = winner_name
        self.loser_names = loser_names

    def __repr__(self) -> str:
        return (
            f"HedgedResult(winner={self.winner_name!r}, "
            f"losers={self.loser_names!r})"
        )


async def hedged_execute(
    providers: list[tuple[BaseProvider, str]],
    request: ChatCompletionRequest,
) -> HedgedResult:
    """
    Fire the same request at up to 2 providers in parallel.
    Return the first response. Cancel all others.

    Args:
        providers: List of (provider, api_key) tuples, max 2.
        request: The chat completion request.

    Returns:
        HedgedResult with the winning response, the winner's name, and
        the names of any losing providers (so callers can update their
        circuit breakers accordingly).

    Raises:
        ValueError: If no providers were given.
        Exception: If all providers fail. The first error is re-raised.
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

    # Cancel all pending tasks immediately. Use CancelledError-specific
    # suppression: when a task is cancelled, awaiting it raises
    # CancelledError. A bare Exception in the suppress tuple would also
    # swallow the original failure if the task had raised before we got
    # here, which would mask real provider errors in our logs.
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Walk done tasks once. If more than one finished before we could
    # cancel (e.g. both providers returned on the same scheduler tick),
    # the first task we pick with no exception is the winner; the rest
    # are losers that need their result fetched (or exception ignored)
    # so the asyncio task machinery doesn't warn about un-awaited tasks.
    winner_task: asyncio.Task[ChatCompletionResponse] | None = None
    winner_provider: BaseProvider | None = None
    loser_providers: list[BaseProvider] = []
    errors: list[BaseException] = []

    for task in done:
        exc = task.exception()
        if exc is None and winner_task is None:
            winner_task = task
            winner_provider = tasks[task]
        elif exc is None:
            loser_providers.append(tasks[task])
        else:
            errors.append(exc)

    if winner_task is not None:
        logger.info("Hedged winner: %s", winner_provider.name)
        # Drain any leftover successful losers so their task objects
        # aren't GC'd in a 'pending result' state — that's a common
        # asyncio footgun that produces "Task was destroyed but it is
        # pending!" warnings at shutdown.
        for loser in loser_providers:
            for t in done:
                if tasks.get(t) is loser:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        t.result()
                    break
        return HedgedResult(
            response=winner_task.result(),
            winner_name=winner_provider.name,
            loser_names=tuple(p.name for p in loser_providers),
        )

    # All done tasks failed
    logger.warning("All hedged providers failed (%d errors)", len(errors))
    raise errors[0]
