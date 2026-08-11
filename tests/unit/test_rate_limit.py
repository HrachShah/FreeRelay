from unittest.mock import patch

import pytest

from freerelay.middleware.rate_limit import TokenBucket


@pytest.mark.parametrize(
    "rate, capacity",
    [(0, 1), (-1, 1), (float("nan"), 1), (float("inf"), 1), (1, 0), (1, -1)],
)
def test_token_bucket_rejects_non_positive_settings(rate, capacity):
    with pytest.raises(ValueError):
        TokenBucket(rate, capacity)


def test_token_bucket_uses_monotonic_clock_for_refills():
    with patch("freerelay.middleware.rate_limit.time.monotonic", side_effect=[10.0, 10.0, 10.0, 11.0]):
        bucket = TokenBucket(rate=1, capacity=1)
        assert bucket.consume()
        assert not bucket.consume()

        bucket.tokens = 0
        assert bucket.consume()


@pytest.mark.asyncio
async def test_concurrent_requests_share_bucket_atomically():
    from unittest.mock import AsyncMock, Mock

    from freerelay.middleware.rate_limit import RateLimitMiddleware

    middleware = RateLimitMiddleware(Mock(), requests_per_minute=1, burst_capacity=1)
    request = Mock()
    request.url.path = "/v1/chat/completions"
    request.state.user_id = "tenant"
    request.client.host = "127.0.0.1"
    call_next = AsyncMock()

    responses = await __import__("asyncio").gather(
        middleware.dispatch(request, call_next),
        middleware.dispatch(request, call_next),
    )

    assert sum(response.status_code == 429 for response in responses) == 1
    assert call_next.await_count == 1


@pytest.mark.parametrize("rate, capacity", [(True, 1), (1, True), (1.5, 1)])
def test_token_bucket_rejects_wrong_numeric_types(rate, capacity):
    with pytest.raises((TypeError, ValueError)):
        TokenBucket(rate, capacity)
