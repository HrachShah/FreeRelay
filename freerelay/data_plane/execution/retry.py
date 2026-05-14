"""
FreeRelay Data Plane — Retry with Exponential Backoff (§9)
=============================================================
Full jitter backoff with per-provider retry config.
RetryableError classification for HTTP status codes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger("freerelay.data_plane.retry")

T = TypeVar("T")

# HTTP status codes that are retryable
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class RetryableError(Exception):
    """An error that should trigger a retry."""

    def __init__(
        self,
        message: str = "",
        status_code: int | None = None,
        provider: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider
        self.retry_after = retry_after


class NonRetryableError(Exception):
    """An error that should NOT be retried."""

    pass


def classify_error(exc: Exception) -> bool:
    """
    Determine if an exception is retryable.

    Returns:
        True if the error should trigger a retry.
    """
    if isinstance(exc, RetryableError):
        return True

    if isinstance(exc, NonRetryableError):
        return False

    if isinstance(exc, asyncio.TimeoutError):
        return True

    if isinstance(exc, ConnectionError):
        return True

    # Check for HTTP status codes in exception attributes
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code in RETRYABLE_STATUS_CODES

    # Check exception message for common patterns
    msg = str(exc).lower()
    return bool(any(pattern in msg for pattern in ("timeout", "connection", "timed out")))


@dataclass
class RetryConfig:
    """Per-provider retry configuration."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    jitter: bool = True
    retryable_status_codes: set[int] | None = None

    def __post_init__(self) -> None:
        if self.retryable_status_codes is None:
            self.retryable_status_codes = RETRYABLE_STATUS_CODES


async def retry_with_backoff[T](
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_codes: set[int] | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """
    Execute a coroutine factory with exponential backoff and full jitter.

    Args:
        coro_factory: Callable that creates a fresh coroutine each attempt.
                      Must be a factory (not a coroutine) to allow retries.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubled each retry).
        max_delay: Maximum delay cap in seconds.
        jitter: If True, apply full jitter: random(0, delay).
        retryable_codes: HTTP status codes that trigger retry.
        on_retry: Optional callback(attempt, exception) on each retry.

    Returns:
        The result of the successful coroutine.

    Raises:
        The last exception if all retries are exhausted.
    """
    if retryable_codes is None:
        retryable_codes = RETRYABLE_STATUS_CODES

    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except (RetryableError, asyncio.TimeoutError, ConnectionError, OSError) as exc:
            last_exc = exc

            if not classify_error(exc):
                raise

            if attempt >= max_retries:
                logger.warning(
                    "Retry exhausted after %d attempts: %s",
                    attempt + 1,
                    exc,
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2**attempt), max_delay)

            # Apply full jitter
            if jitter:
                delay = random.uniform(0, delay)

            # Honor Retry-After header if present
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None and retry_after > 0:
                delay = max(delay, retry_after)

            logger.info(
                "Retry %d/%d after %.2fs: %s",
                attempt + 1,
                max_retries,
                delay,
                exc,
            )

            if on_retry:
                with contextlib.suppress(Exception):
                    on_retry(attempt, exc)

            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Retry loop exited without result or exception")


async def retry_with_config[T](
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    config: RetryConfig,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """Convenience wrapper using RetryConfig."""
    return await retry_with_backoff(
        coro_factory=coro_factory,
        max_retries=config.max_retries,
        base_delay=config.base_delay,
        max_delay=config.max_delay,
        jitter=config.jitter,
        retryable_codes=config.retryable_status_codes,
        on_retry=on_retry,
    )
