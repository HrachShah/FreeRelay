import pytest

from freerelay.data_plane.execution.retry import (
    RetryableError,
    classify_error,
    retry_with_backoff,
)


def test_classify_error_uses_custom_status_codes() -> None:
    error = RetryableError(status_code=418)

    assert not classify_error(error)
    assert classify_error(error, {418})


@pytest.mark.asyncio
async def test_retry_with_backoff_honors_custom_status_codes() -> None:
    attempts = 0

    async def call() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryableError(status_code=418)
        return "ok"

    result = await retry_with_backoff(
        call,
        max_retries=1,
        base_delay=0,
        max_delay=0,
        jitter=False,
        retryable_codes={418},
    )

    assert result == "ok"
    assert attempts == 2


@pytest.mark.asyncio
async def test_retry_with_backoff_does_not_retry_unlisted_status_codes() -> None:
    attempts = 0

    async def call() -> str:
        nonlocal attempts
        attempts += 1
        raise RetryableError(status_code=418)

    with pytest.raises(RetryableError):
        await retry_with_backoff(
            call,
            max_retries=1,
            base_delay=0,
            max_delay=0,
            jitter=False,
            retryable_codes={503},
        )

    assert attempts == 1
