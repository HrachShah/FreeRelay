"""
FreeRelay — Retry with Exponential Backoff + Jitter (§11)
============================================================
Implements retry logic with exponential backoff and jitter
to prevent thundering herd problems.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger("freerelay.retry")

T = TypeVar("T")


async def retry_with_backoff[T](
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Retry an async function with exponential backoff and optional jitter.

    Args:
        func: Async callable to retry.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        jitter: Add random jitter to prevent thundering herd.
        retryable_exceptions: Tuple of exception types that trigger retry.

    Returns:
        Result of the function call.

    Raises:
        Exception: The last exception if all retries fail.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_error = e
            if attempt >= max_retries:
                break

            delay = min(base_delay * (2**attempt), max_delay)
            if jitter:
                delay *= 0.5 + random.random() * 0.5  # 50-100% of delay

            logger.warning(
                "Retry %d/%d after %.2fs: %s",
                attempt + 1,
                max_retries,
                delay,
                str(e)[:100],
            )
            await asyncio.sleep(delay)

    raise last_error or RuntimeError("All retries exhausted")


def calculate_backoff(
    attempt: int,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    jitter: bool = True,
) -> float:
    """
    Calculate backoff delay for a given attempt number.

    Args:
        attempt: Current attempt number (0-indexed).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap.
        jitter: Whether to add random jitter.

    Returns:
        Delay in seconds.
    """
    delay = min(base_delay * (2**attempt), max_delay)
    if jitter:
        delay *= 0.5 + random.random() * 0.5
    return delay
