from unittest.mock import AsyncMock, Mock

import pytest

from freerelay.middleware.rate_limit import RateLimitMiddleware, TokenBucket


@pytest.mark.asyncio
async def test_health_and_metrics_paths_bypass_rate_limit():
    middleware = RateLimitMiddleware(Mock(), requests_per_minute=60, burst_capacity=1)
    call_next = AsyncMock(return_value=Mock())

    for path in ("/v1/health", "/v1/health/check", "/v1/metrics", "/v1/metrics/prometheus"):
        request = Mock()
        request.url.path = path
        request.state = type("State", (), {})()
        request.client = None
        await middleware.dispatch(request, call_next)

    assert call_next.await_count == 4
    assert middleware._buckets == {}


@pytest.mark.asyncio
async def test_similarly_named_endpoint_is_still_rate_limited():
    middleware = RateLimitMiddleware(Mock(), requests_per_minute=60, burst_capacity=1)
    call_next = AsyncMock(return_value=Mock())
    request = Mock()
    request.url.path = "/v1/healthcheck"
    request.state.user_id = "user-1"
    request.client.host = "127.0.0.1"

    await middleware.dispatch(request, call_next)
    await middleware.dispatch(request, call_next)

    assert call_next.await_count == 1
    assert middleware._buckets["user-1"].tokens < 1


def test_token_bucket_uses_monotonic_time_for_refills(monkeypatch: pytest.MonkeyPatch) -> None:
    wall_clock = iter((100.0, 99.0, 98.0))
    monotonic_clock = iter((10.0, 10.0, 10.0, 11.0))
    monkeypatch.setattr("freerelay.middleware.rate_limit.time.time", lambda: next(wall_clock))
    monkeypatch.setattr(
        "freerelay.middleware.rate_limit.time.monotonic",
        lambda: next(monotonic_clock),
    )
    bucket = TokenBucket(rate=1.0, capacity=1)

    assert bucket.consume()
    assert not bucket.consume()
    assert bucket.consume()
